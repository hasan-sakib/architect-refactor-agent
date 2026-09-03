import asyncio
from pathlib import Path

from app.agent.graph import build_graph
from app.agent.state import AgentContext, initial_state
from app.api.schemas import TaskCreateRequest
from app.api.task_manager import TaskRecord, task_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.drivers.base import SandboxConfig
from app.drivers.docker_driver import DockerSandboxDriver

logger = get_logger(__name__)
settings = get_settings()
BACKEND_DIR = Path(__file__).resolve().parents[2]


def execute_task(record: TaskRecord, loop: asyncio.AbstractEventLoop, req: TaskCreateRequest) -> None:
    """Runs the LangGraph agent to completion against a fresh sandbox,
    streaming a state-update event after every node. Runs on a worker thread
    (dispatched via FastAPI's BackgroundTasks), so all cross-thread event
    delivery goes through task_manager.emit's call_soon_threadsafe."""
    record.status = "running"
    task_manager.emit(loop, record, {"type": "status", "status": "running"})

    driver = None
    try:
        config = SandboxConfig(
            workspace_path=req.repo_path,
            image=settings.sandbox_image,
            mount_path=settings.SANDBOX_WORKSPACE_MOUNT,
            mem_limit=settings.SANDBOX_MEM_LIMIT,
            nano_cpus=settings.sandbox_nano_cpus,
            network_disabled=settings.SANDBOX_NETWORK_DISABLED,
            name=f"task-{record.id}",
        )
        driver = DockerSandboxDriver(config)

        task_manager.emit(loop, record, {"type": "log", "message": "Building sandbox image..."})
        driver.build(dockerfile_dir=str(BACKEND_DIR), dockerfile_name=settings.SANDBOX_DOCKERFILE_PATH)

        task_manager.emit(loop, record, {"type": "log", "message": "Starting sandbox container..."})
        driver.start()

        graph = build_graph()
        context = AgentContext(driver=driver, vector_store=None)
        state = initial_state(task=req.task, test_command=req.test_command, max_iterations=req.max_iterations)

        final_state = dict(state)
        for step in graph.stream(state, context=context, stream_mode="updates"):
            for node_name, node_output in step.items():
                final_state.update(node_output)
                task_manager.emit(loop, record, {"type": "node", "node": node_name, "data": node_output})

        record.final_state = final_state
        record.status = final_state["status"]
        task_manager.emit(
            loop, record, {"type": "done", "status": record.status, "final_state": final_state}
        )
    except Exception as e:
        logger.exception("task %s failed", record.id)
        record.status = "error"
        record.final_state = {"error": str(e)}
        task_manager.emit(loop, record, {"type": "error", "message": str(e)})
    finally:
        if driver is not None:
            try:
                driver.stop()
                driver.cleanup()
            except Exception:
                logger.exception("failed to clean up sandbox for task %s", record.id)
        task_manager.close(loop, record)
