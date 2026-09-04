import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.schemas import TaskCreateRequest
from app.db.models import Task, TaskEvent, Upload
from app.core.logging import get_logger

logger = get_logger(__name__)

ACTIVE_STATUSES = ("pending", "queued", "running")
MAX_EVENT_PAYLOAD_BYTES = 256 * 1024


def _truncate_payload(event: dict) -> dict:
    """Event payloads can carry full before/after file contents or raw test
    output — cap what actually gets persisted so one adversarial or noisy
    task can't bloat the events table without bound."""
    encoded = json.dumps(event)
    if len(encoded.encode("utf-8")) <= MAX_EVENT_PAYLOAD_BYTES:
        return event

    def shrink(value):
        if isinstance(value, str) and len(value) > 2000:
            return value[:2000] + f"...[truncated {len(value) - 2000} chars]"
        if isinstance(value, dict):
            return {k: shrink(v) for k, v in value.items()}
        if isinstance(value, list):
            return [shrink(v) for v in value]
        return value

    return shrink(event)


def create_task(db: Session, *, user_id: uuid.UUID, upload_id: uuid.UUID, repo_path: str, req: TaskCreateRequest) -> Task:
    task = Task(
        user_id=user_id,
        upload_id=upload_id,
        repo_path=repo_path,
        task=req.task,
        test_command=req.test_command,
        max_iterations=req.max_iterations,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).one_or_none()


def list_tasks(db: Session, *, user_id: uuid.UUID, limit: int = 50) -> list[Task]:
    return (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
        .all()
    )


def append_event(db: Session, task_id: uuid.UUID, *, seq: int, event: dict) -> None:
    db.add(TaskEvent(task_id=task_id, seq=seq, type=event["type"], payload=_truncate_payload(event)))
    db.commit()


def get_events(db: Session, task_id: uuid.UUID, *, after_seq: int = 0) -> list[dict]:
    rows = (
        db.query(TaskEvent)
        .filter(TaskEvent.task_id == task_id, TaskEvent.seq > after_seq)
        .order_by(TaskEvent.seq.asc())
        .all()
    )
    return [row.payload for row in rows]


def mark_running(db: Session, task_id: uuid.UUID) -> None:
    db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(status="running", started_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    )
    db.commit()


def mark_finished(db: Session, task_id: uuid.UUID, *, status: str, final_state: Optional[dict], error: Optional[str]) -> None:
    db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(
            status=status,
            final_state=final_state,
            error=error,
            finished_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def reconcile_orphaned(db: Session) -> int:
    """Marks any task left in an active status as interrupted. Correct ONLY
    because this runs once from a single-process lifespan on startup — with
    multiple backend replicas this would wrongly kill another replica's
    genuinely-running tasks (see docs/architecture.md's multi-replica note)."""
    result = db.execute(
        update(Task)
        .where(Task.status.in_(ACTIVE_STATUSES))
        .values(
            status="error",
            error="interrupted by server restart",
            finished_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    count = result.rowcount or 0
    if count:
        logger.warning("reconciled %d orphaned task(s) on startup", count)
    return count


def active_repo_paths(db: Session) -> set[str]:
    rows = db.query(Task.repo_path).filter(Task.status.in_(ACTIVE_STATUSES)).all()
    return {row[0] for row in rows}


def create_upload(db: Session, *, user_id: uuid.UUID, repo_path: str, file_count: int, total_bytes: int) -> Upload:
    upload = Upload(user_id=user_id, repo_path=repo_path, file_count=file_count, total_bytes=total_bytes)
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


def get_upload(db: Session, upload_id: uuid.UUID, *, user_id: uuid.UUID) -> Optional[Upload]:
    return (
        db.query(Upload)
        .filter(Upload.id == upload_id, Upload.user_id == user_id, Upload.status == "ready")
        .one_or_none()
    )


def get_or_create_local_upload(db: Session, *, user_id: uuid.UUID, repo_path: str) -> Upload:
    """Local/admin escape hatch for AUTH_MODE=disabled + ALLOW_ARBITRARY_REPO_PATH:
    a raw repo_path string still needs an uploads row to satisfy tasks.upload_id's
    FK, so upsert a lightweight record around it rather than making the FK
    nullable just for this one deprecated path."""
    existing = db.query(Upload).filter(Upload.repo_path == repo_path, Upload.user_id == user_id).one_or_none()
    if existing is not None:
        return existing
    upload = Upload(user_id=user_id, repo_path=repo_path, file_count=0, total_bytes=0)
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload
