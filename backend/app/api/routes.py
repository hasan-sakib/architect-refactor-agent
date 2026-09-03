import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.executor import execute_task
from app.api.schemas import TaskCreateRequest, TaskCreateResponse, TaskStatusResponse, UploadResponse
from app.api.task_manager import task_manager
from app.core.config import get_settings

router = APIRouter(prefix="/api")
settings = get_settings()

SSE_KEEPALIVE_SECONDS = 15


def _safe_relative_path(raw: str) -> Path:
    """Rejects absolute paths and any '..' segment — raw is a browser-supplied
    filename (we ask the frontend to send each file's folder-relative path as
    its multipart filename), so it must be treated as untrusted input."""
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail=f"invalid path in upload: {raw!r}")
    return Path(*parts)


@router.post("/uploads", response_model=UploadResponse)
async def upload_repository(files: list[UploadFile] = File(...)) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")

    dest_root = Path(settings.upload_root) / uuid.uuid4().hex[:12]
    dest_root.mkdir(parents=True, exist_ok=True)

    for upload in files:
        relative = _safe_relative_path(upload.filename or "")
        dest_path = dest_root / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(await upload.read())

    return UploadResponse(repo_path=str(dest_root), file_count=len(files))


@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(req: TaskCreateRequest, background_tasks: BackgroundTasks) -> TaskCreateResponse:
    if not Path(req.repo_path).is_dir():
        raise HTTPException(status_code=400, detail=f"repo_path does not exist: {req.repo_path}")

    record = task_manager.create()
    loop = asyncio.get_running_loop()
    background_tasks.add_task(execute_task, record, loop, req)
    return TaskCreateResponse(task_id=record.id)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    record = task_manager.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskStatusResponse(
        id=record.id, status=record.status, events=record.events, final_state=record.final_state
    )


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request) -> StreamingResponse:
    record = task_manager.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    queue = task_manager.subscribe(record)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if item is None:
                    yield "event: end\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            task_manager.unsubscribe(record, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
