from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    upload_id: Optional[UUID] = None
    # Deprecated production path: only honored when AUTH_MODE=disabled or
    # ALLOW_ARBITRARY_REPO_PATH=true (local/admin use). The public product is
    # uploads-only — see docs/architecture.md.
    repo_path: Optional[str] = Field(default=None, max_length=4096)
    task: str = Field(min_length=1, max_length=4000)
    test_command: str = Field(min_length=1, max_length=500)
    max_iterations: int = Field(default=3, ge=0, le=3)


class TaskCreateResponse(BaseModel):
    task_id: str


class TaskSummary(BaseModel):
    id: str
    status: str
    task: str
    created_at: str
    finished_at: Optional[str] = None


class TaskStatusResponse(BaseModel):
    id: str
    status: str
    events: list[dict]
    final_state: Optional[dict] = None


class StreamTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class UploadResponse(BaseModel):
    upload_id: str
    repo_path: str
    file_count: int


class ClientConfigResponse(BaseModel):
    allow_host_paths: bool
    max_upload_bytes: int
    max_upload_files: int
    max_iterations_cap: int
