import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import task_store
from app.api.deps import CurrentUser, DbSession
from app.api.event_bus import event_bus
from app.api.executor import TaskRunContext, submit_task
from app.api.schemas import (
    ClientConfigResponse,
    StreamTicketResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
    TaskSummary,
    UploadResponse,
)
from app.core.auth import TokenError
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retention import check_disk_space
from app.core.stream_ticket import issue_stream_ticket, verify_stream_ticket

logger = get_logger(__name__)

router = APIRouter(prefix="/api")
settings = get_settings()

SSE_KEEPALIVE_SECONDS = 15
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _safe_relative_path(raw: str) -> Path:
    """Rejects absolute paths and any '..' segment — raw is a browser-supplied
    filename (we ask the frontend to send each file's folder-relative path as
    its multipart filename), so it must be treated as untrusted input."""
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail=f"invalid path in upload: {raw!r}")
    return Path(*parts)


@router.get("/config", response_model=ClientConfigResponse)
def client_config() -> ClientConfigResponse:
    return ClientConfigResponse(
        allow_host_paths=settings.ALLOW_ARBITRARY_REPO_PATH,
        max_upload_bytes=settings.MAX_UPLOAD_BYTES,
        max_upload_files=settings.MAX_UPLOAD_FILES,
        max_iterations_cap=3,
    )


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    """Uploaded files are written by the backend (root in the container);
    Dockerfile.sandbox runs as uid 1000. Without this, the Coder node's first
    write_file() into /workspace fails with Permission denied — masked on
    macOS Docker Desktop's FUSE layer, real on a Linux VM. Harmless no-op
    failure on native (non-Docker) dev, where the backend runs as a normal
    unprivileged user and can't chown to an arbitrary uid anyway."""
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            os.chown(dirpath, uid, gid)
            for name in filenames:
                os.chown(os.path.join(dirpath, name), uid, gid)
    except (PermissionError, OSError):
        pass


@router.post("/uploads", response_model=UploadResponse)
async def upload_repository(user: CurrentUser, db: DbSession, files: list[UploadFile] = File(...)) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")
    if len(files) > settings.MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"too many files (max {settings.MAX_UPLOAD_FILES})")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="server is temporarily out of upload capacity")

    dest_root = Path(settings.upload_root) / str(user.id) / uuid.uuid4().hex[:12]
    dest_root.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    try:
        for upload in files:
            relative = _safe_relative_path(upload.filename or "")
            dest_path = dest_root / relative
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            file_bytes = 0
            with dest_path.open("wb") as fh:
                while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if file_bytes > settings.MAX_UPLOAD_FILE_BYTES:
                        raise HTTPException(status_code=413, detail=f"file too large: {upload.filename}")
                    if total_bytes > settings.MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="upload exceeds total size limit")
                    fh.write(chunk)
    except BaseException:
        shutil.rmtree(dest_root, ignore_errors=True)
        raise

    _chown_tree(dest_root, settings.SANDBOX_UID, settings.SANDBOX_GID)

    upload_row = task_store.create_upload(
        db, user_id=user.id, repo_path=str(dest_root), file_count=len(files), total_bytes=total_bytes
    )
    return UploadResponse(upload_id=str(upload_row.id), repo_path=str(dest_root), file_count=len(files))


@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(req: TaskCreateRequest, user: CurrentUser, db: DbSession) -> TaskCreateResponse:
    if req.upload_id is not None:
        upload = task_store.get_upload(db, req.upload_id, user_id=user.id)
        if upload is None:
            raise HTTPException(status_code=404, detail="upload not found")
        repo_path = upload.repo_path
    elif req.repo_path and settings.ALLOW_ARBITRARY_REPO_PATH:
        repo_path = req.repo_path
        if not Path(repo_path).is_dir():
            raise HTTPException(status_code=400, detail=f"repo_path does not exist: {repo_path}")
        upload = task_store.get_or_create_local_upload(db, user_id=user.id, repo_path=repo_path)
    else:
        raise HTTPException(status_code=400, detail="upload_id is required")

    user_active = task_store.count_active_tasks(db, user_id=user.id)
    if user_active >= settings.MAX_TASKS_PER_USER:
        raise HTTPException(status_code=429, detail="you already have a task running — wait for it to finish")
    total_active = task_store.count_active_tasks(db)
    if total_active >= settings.MAX_CONCURRENT_TASKS:
        raise HTTPException(status_code=429, detail="server is at capacity — try again shortly")

    task = task_store.create_task(db, user_id=user.id, upload_id=upload.id, repo_path=repo_path, req=req)

    loop = asyncio.get_running_loop()
    ctx = TaskRunContext(task_id=task.id, user_id=user.id, repo_path=repo_path, loop=loop)
    submit_task(ctx, req)
    return TaskCreateResponse(task_id=str(task.id))


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(user: CurrentUser, db: DbSession) -> list[TaskSummary]:
    tasks = task_store.list_tasks(db, user_id=user.id)
    return [
        TaskSummary(
            id=str(t.id),
            status=t.status,
            task=t.task,
            created_at=t.created_at.isoformat(),
            finished_at=t.finished_at.isoformat() if t.finished_at else None,
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TaskStatusResponse:
    task = task_store.get_task(db, task_id, user_id=user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    events = task_store.get_events(db, task_id)
    return TaskStatusResponse(id=str(task.id), status=task.status, events=events, final_state=task.final_state)


@router.post("/tasks/{task_id}/stream-ticket", response_model=StreamTicketResponse)
def create_stream_ticket(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> StreamTicketResponse:
    task = task_store.get_task(db, task_id, user_id=user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    ticket, ttl = issue_stream_ticket(user_id=user.id, task_id=task_id)
    return StreamTicketResponse(ticket=ticket, expires_in=ttl)


@router.get("/tasks/{task_id}/stream")
async def stream_task(
    task_id: uuid.UUID,
    request: Request,
    db: DbSession,
    ticket: str = Query(...),
    after_seq: int = Query(default=0),
) -> StreamingResponse:
    try:
        user_id = verify_stream_ticket(ticket, task_id=task_id)
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    task = task_store.get_task(db, task_id, user_id=user_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    task_id_str = str(task_id)
    # Subscribe BEFORE reading history — otherwise an event published between
    # the read and the subscribe call would be lost forever.
    queue = event_bus.subscribe(task_id_str)
    history = task_store.get_events(db, task_id, after_seq=after_seq)
    max_replayed_seq = history[-1]["seq"] if history else after_seq
    is_terminal = task.status in ("passed", "failed", "error")

    async def event_generator():
        try:
            for event in history:
                yield f"data: {json.dumps(event)}\n\n"

            if is_terminal:
                yield "event: end\ndata: {}\n\n"
                return

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
                if item.get("seq", 0) <= max_replayed_seq:
                    continue  # already sent via history replay
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            event_bus.unsubscribe(task_id_str, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
