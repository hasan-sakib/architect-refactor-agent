import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

TERMINAL_STATUSES = {"passed", "failed", "error"}


@dataclass
class TaskRecord:
    id: str
    status: str = "pending"
    events: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    final_state: Optional[dict] = None


class TaskManager:
    """In-memory task registry for this local, single-user tool. Execution
    runs in a worker thread (via FastAPI's BackgroundTasks); events cross
    from that thread to the asyncio event loop via loop.call_soon_threadsafe."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self) -> TaskRecord:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(id=task_id)
        self._tasks[task_id] = record
        return record

    def get(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def emit(self, loop: asyncio.AbstractEventLoop, record: TaskRecord, event: dict) -> None:
        record.events.append(event)
        for queue in list(record.subscribers):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def close(self, loop: asyncio.AbstractEventLoop, record: TaskRecord) -> None:
        for queue in list(record.subscribers):
            loop.call_soon_threadsafe(queue.put_nowait, None)

    def subscribe(self, record: TaskRecord) -> asyncio.Queue:
        """Returns a queue that will receive future events. If the task has
        already finished, the queue is pre-loaded with a terminal event and a
        close sentinel so a late subscriber doesn't hang waiting forever."""
        queue: asyncio.Queue = asyncio.Queue()
        if record.status in TERMINAL_STATUSES:
            queue.put_nowait({"type": "done", "status": record.status, "final_state": record.final_state})
            queue.put_nowait(None)
        else:
            record.subscribers.append(queue)
        return queue

    def unsubscribe(self, record: TaskRecord, queue: asyncio.Queue) -> None:
        if queue in record.subscribers:
            record.subscribers.remove(queue)


task_manager = TaskManager()
