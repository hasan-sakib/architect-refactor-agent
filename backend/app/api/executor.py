import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from app.agent.graph import build_graph
from app.agent.state import AgentContext, initial_state
from app.api import task_store
from app.api.event_bus import event_bus
from app.api.schemas import TaskCreateRequest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.drivers.base import SandboxConfig
from app.drivers.docker_driver import DockerSandboxDriver

logger = get_logger(__name__)
settings = get_settings()
BACKEND_DIR = Path(__file__).resolve().parents[2]

# Bounded, not BackgroundTasks' unbounded-thread-per-request: on a public
# deployment N simultaneous callers must not each get their own Docker build
# + sandbox container with zero ceiling.
_pool = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_TASKS, thread_name_prefix="task-executor")


@dataclass
class TaskRunContext:
    task_id: uuid.UUID
    user_id: uuid.UUID
    repo_path: str
    loop: asyncio.AbstractEventLoop
    seq: int = 0


def submit_task(ctx: TaskRunContext, req: TaskCreateRequest) -> None:
    _pool.submit(execute_task, ctx, req)


def execute_task(ctx: TaskRunContext, req: TaskCreateRequest) -> None:
    """Runs the LangGraph agent to completion against a fresh sandbox,
    persisting an event after every node before publishing it live — a
    client that reconnects and replays from Postgres must never see a
    shorter history than it already rendered while connected."""
    task_id_str = str(ctx.task_id)

    def emit(event: dict) -> None:
        ctx.seq += 1
        event = {**event, "seq": ctx.seq, "ts": time.time()}
        try:
            with session_scope() as db:
                task_store.append_event(db, ctx.task_id, seq=event["seq"], event=event)
        except Exception:
            logger.exception("failed to persist event for task %s", task_id_str)
        event_bus.publish(ctx.loop, task_id_str, event)

    with session_scope() as db:
        task_store.mark_running(db, ctx.task_id)
    emit({"type": "status", "status": "running"})

    driver = None
    watchdog: threading.Timer | None = None
    final_state: dict = {}
    status = "error"
    error_message: str | None = None
    timed_out = False
    try:
        config = SandboxConfig(
            workspace_path=ctx.repo_path,
            image=settings.sandbox_image,
            mount_path=settings.SANDBOX_WORKSPACE_MOUNT,
            mem_limit=settings.SANDBOX_MEM_LIMIT,
            memswap_limit=settings.SANDBOX_MEM_LIMIT,
            nano_cpus=settings.sandbox_nano_cpus,
            pids_limit=settings.SANDBOX_PIDS_LIMIT,
            user=f"{settings.SANDBOX_UID}:{settings.SANDBOX_GID}",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            tmpfs={"/tmp": "rw,nosuid,size=512m"},
            network_disabled=settings.SANDBOX_NETWORK_DISABLED,
            network=settings.SANDBOX_NETWORK_NAME,
            name=f"task-{ctx.task_id.hex[:12]}",
        )
        driver = DockerSandboxDriver(config)

        emit({"type": "log", "message": "Building sandbox image..."})
        driver.build(dockerfile_dir=str(BACKEND_DIR), dockerfile_name=settings.SANDBOX_DOCKERFILE_PATH)

        emit({"type": "log", "message": "Starting sandbox container..."})
        driver.start()

        # Hard watchdog: the graph-step deadline check below only fires
        # *between* nodes, so it can't interrupt an in-flight blocked
        # exec_run (e.g. a test command ignoring its own timeout, or a hung
        # LLM call). Stopping the container from this timer thread makes
        # any in-flight exec_run return, which is what actually unwedges it.
        def _on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            try:
                driver.stop(timeout=5)
            except Exception:
                logger.exception("watchdog failed to stop sandbox for task %s", task_id_str)

        watchdog = threading.Timer(settings.TASK_MAX_WALL_SECONDS, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

        graph = build_graph()
        context = AgentContext(driver=driver, vector_store=None)
        state = initial_state(task=req.task, test_command=req.test_command, max_iterations=req.max_iterations)
        deadline = time.monotonic() + settings.TASK_MAX_WALL_SECONDS

        final_state = dict(state)
        for step in graph.stream(state, context=context, stream_mode="updates"):
            for node_name, node_output in step.items():
                final_state.update(node_output)
                emit({"type": "node", "node": node_name, "data": node_output})
            if time.monotonic() > deadline or timed_out:
                raise TimeoutError(f"task exceeded {settings.TASK_MAX_WALL_SECONDS}s wall-clock limit")

        status = final_state["status"]
        emit({"type": "done", "status": status, "final_state": final_state})
    except Exception as e:
        logger.exception("task %s failed", task_id_str)
        status = "error"
        error_message = str(e) if not timed_out else f"task exceeded {settings.TASK_MAX_WALL_SECONDS}s wall-clock limit"
        final_state = {"error": error_message}
        emit({"type": "error", "message": error_message})
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if driver is not None:
            try:
                driver.stop()
                driver.cleanup()
            except Exception:
                logger.exception("failed to clean up sandbox for task %s", task_id_str)
        with session_scope() as db:
            task_store.mark_finished(db, ctx.task_id, status=status, final_state=final_state, error=error_message)
        event_bus.close(ctx.loop, task_id_str)
