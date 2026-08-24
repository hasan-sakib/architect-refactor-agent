from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import coder_node, planner_node, self_healer_node, tester_node
from app.agent.state import AgentContext, AgentState


def _route_after_tester(state: AgentState) -> str:
    return END if state["status"] in ("passed", "failed") else "self_healer"


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState, context_schema=AgentContext)

    graph.add_node("planner", planner_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)
    graph.add_node("self_healer", self_healer_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "coder")
    graph.add_edge("coder", "tester")
    graph.add_conditional_edges("tester", _route_after_tester, {END: END, "self_healer": "self_healer"})
    graph.add_edge("self_healer", "coder")

    return graph.compile()
