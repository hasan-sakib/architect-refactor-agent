import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Task, Upload
from app.db.session import session_scope

settings = get_settings()
logger = get_logger(__name__)


def _active_repo_paths(db: Session) -> set[str]:
    """Uploads currently mounted into a running sandbox must never be
    deleted out from under it — mid-run deletion produces confusing
    failures, not a clean error."""
    rows = db.execute(select(Task.repo_path).where(Task.status.in_(("pending", "queued", "running")))).all()
    return {row[0] for row in rows}


def _is_expired(upload: Upload, now: datetime) -> bool:
    ttl_cutoff = now - timedelta(hours=settings.UPLOAD_RETENTION_HOURS)
    if upload.created_at.replace(tzinfo=timezone.utc) < ttl_cutoff:
        return True

    grace_cutoff = now - timedelta(minutes=settings.UPLOAD_POST_TASK_GRACE_MINUTES)
    # An upload is "done with its task" once every task against it has
    # finished; approximate via: no active task references it AND it's
    # older than the grace window. Good enough without a dedicated join.
    return upload.created_at.replace(tzinfo=timezone.utc) < grace_cutoff


def purge_expired_uploads(db: Session) -> tuple[int, int]:
    """Deletes expired upload directories from disk and marks their rows
    'deleted'. Returns (dirs_removed, bytes_freed)."""
    active_paths = _active_repo_paths(db)
    now = datetime.now(timezone.utc)

    candidates = db.execute(select(Upload).where(Upload.status == "ready")).scalars().all()

    removed = 0
    freed = 0
    for upload in candidates:
        if upload.repo_path in active_paths:
            continue
        if not _is_expired(upload, now):
            continue

        path = Path(upload.repo_path)
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            logger.exception("failed to remove expired upload dir %s", upload.repo_path)
            continue

        db.execute(update(Upload).where(Upload.id == upload.id).values(status="deleted", deleted_at=now))
        removed += 1
        freed += upload.total_bytes

    db.commit()
    if removed:
        logger.info("retention sweep: removed %d upload(s), freed %d bytes", removed, freed)
    return removed, freed


def check_disk_space() -> bool:
    """Returns True if there's enough free space to accept new uploads."""
    try:
        usage = shutil.disk_usage(settings.upload_root)
    except OSError:
        return True  # upload_root doesn't exist yet — nothing to check
    if usage.free < 5 * 1024 * 1024 * 1024:  # 5 GiB floor
        logger.warning("low disk space on upload volume: %d bytes free", usage.free)
        return False
    return True


def run_retention_sweep() -> None:
    with session_scope() as db:
        purge_expired_uploads(db)
