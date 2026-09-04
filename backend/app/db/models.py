import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    """Soft-references Supabase auth.users.id (the JWT 'sub' claim) — no
    cross-schema FK, since Alembic must never see Supabase-managed schemas
    and local dev has no `auth` schema at all. Populated by lazy upsert on
    first authenticated request, not a trigger."""

    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (UniqueConstraint("repo_path", name="uploads_repo_path_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    repo_path: Mapped[str] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(Integer)
    total_bytes: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ready'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="RESTRICT")
    )
    repo_path: Mapped[str] = mapped_column(Text)  # denormalized snapshot at submit time
    task: Mapped[str] = mapped_column(Text)
    test_command: Mapped[str] = mapped_column(Text)
    max_iterations: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), index=True)
    final_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class TaskEvent(Base):
    """Append-only, seq-ordered per task — replaces the old in-memory
    TaskRecord.events list. seq lets a reconnecting SSE client replay
    exactly what it missed via `after_seq`."""

    __tablename__ = "task_events"
    __table_args__ = (UniqueConstraint("task_id", "seq", name="task_events_task_seq_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
