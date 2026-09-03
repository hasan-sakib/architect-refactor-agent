from dataclasses import dataclass
from typing import Literal, Optional, TypedDict

from app.drivers.base import BaseSandboxDriver
from app.rag.vector_store import VectorStoreManager

AgentStatus = Literal["planning", "coding", "testing", "healing", "passed", "failed"]


class AgentState(TypedDict):
    task: str
    test_command: str
    plan: str
    error_context: str
    files_changed: list[dict]  # [{"path": str, "before": str, "after": str}, ...]
    test_output: str
    test_exit_code: Optional[int]
    iteration: int
    max_iterations: int
    status: AgentStatus


@dataclass
class AgentContext:
    """Run-scoped dependencies injected via LangGraph's context_schema —
    kept out of AgentState since a live sandbox driver / vector store handle
    isn't state that should be serialized or checkpointed."""

    driver: BaseSandboxDriver
    vector_store: Optional[VectorStoreManager] = None


def initial_state(task: str, test_command: str, max_iterations: int = 3) -> AgentState:
    return AgentState(
        task=task,
        test_command=test_command,
        plan="",
        error_context="",
        files_changed=[],
        test_output="",
        test_exit_code=None,
        iteration=0,
        max_iterations=max_iterations,
        status="planning",
    )
