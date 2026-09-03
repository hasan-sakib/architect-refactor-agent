from typing import Optional

from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    repo_path: str
    task: str
    test_command: str
    max_iterations: int = 3


class TaskCreateResponse(BaseModel):
    task_id: str


class TaskStatusResponse(BaseModel):
    id: str
    status: str
    events: list[dict]
    final_state: Optional[dict] = None
