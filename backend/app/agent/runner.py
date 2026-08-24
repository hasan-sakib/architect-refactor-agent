from typing import Optional

from app.agent.graph import build_graph
from app.agent.state import AgentContext, AgentState, initial_state
from app.drivers.base import BaseSandboxDriver
from app.rag.vector_store import VectorStoreManager


def run_refactor_task(
    task: str,
    test_command: str,
    driver: BaseSandboxDriver,
    vector_store: Optional[VectorStoreManager] = None,
    max_iterations: int = 3,
) -> AgentState:
    """Run the Planner -> Coder -> Tester -> SelfHealer graph to completion
    against an already-started sandbox `driver`. Returns the final state."""
    graph = build_graph()
    context = AgentContext(driver=driver, vector_store=vector_store)
    state = initial_state(task=task, test_command=test_command, max_iterations=max_iterations)
    return graph.invoke(state, context=context)
