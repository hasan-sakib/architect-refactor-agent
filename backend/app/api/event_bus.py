import asyncio
from collections import defaultdict


class EventBus:
    """In-process SSE fan-out, keyed by task_id. Mechanism is unchanged from
    the old TaskManager: the executor runs on a worker thread and crosses
    into the event loop via loop.call_soon_threadsafe. Task *state* is durable
    (task_store.py, Postgres); this class only carries live delivery to
    whoever happens to be connected right now — a reconnecting client always
    catches up via task_store.get_events(after_seq=...) instead."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(task_id)
        if subs and queue in subs:
            subs.remove(queue)
        if subs is not None and not subs:
            self._subscribers.pop(task_id, None)

    def publish(self, loop: asyncio.AbstractEventLoop, task_id: str, event: dict) -> None:
        for queue in list(self._subscribers.get(task_id, ())):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def close(self, loop: asyncio.AbstractEventLoop, task_id: str) -> None:
        for queue in list(self._subscribers.get(task_id, ())):
            loop.call_soon_threadsafe(queue.put_nowait, None)


event_bus = EventBus()
