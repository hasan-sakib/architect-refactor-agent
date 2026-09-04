import re

from langgraph.runtime import Runtime

from app.agent.prompts import (
    CODER_SYSTEM_PROMPT,
    CODER_USER_TEMPLATE,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    SELF_HEALER_SYSTEM_PROMPT,
    SELF_HEALER_USER_TEMPLATE,
    render_error_section,
)
from app.agent.state import AgentContext, AgentState
from app.core.config import get_settings
from app.core.llm import get_completion
from app.core.logging import get_logger
from app.tools.exec_tools import run_command
from app.tools.file_tools import read_file, write_file
from app.tools.search_tools import format_search_results, search_codebase

logger = get_logger(__name__)
settings = get_settings()

FILE_BLOCK_RE = re.compile(r"###\s*FILE:\s*(?P<path>.+?)\s*\n(?P<content>.*?)\n###\s*END FILE", re.DOTALL)


def planner_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    context = "(no vector store configured)"
    if runtime.context.vector_store is not None:
        results = search_codebase(runtime.context.vector_store, state["task"], n_results=5)
        context = format_search_results(results)

    plan = get_completion(
        [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": PLANNER_USER_TEMPLATE.format(task=state["task"], context=context)},
        ]
    )
    logger.info("planner produced plan (%d chars)", len(plan))
    return {"plan": plan, "status": "coding"}


def coder_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    response = get_completion(
        [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": CODER_USER_TEMPLATE.format(
                    task=state["task"],
                    plan=state["plan"],
                    error_section=render_error_section(state["error_context"]),
                ),
            },
        ]
    )

    files_changed = []
    for match in FILE_BLOCK_RE.finditer(response):
        path = match.group("path").strip()
        content = match.group("content")
        try:
            before = read_file(runtime.context.driver, path)
        except Exception:
            before = ""  # new file — nothing to diff against
        write_file(runtime.context.driver, path, content)
        files_changed.append({"path": path, "before": before, "after": content})

    if not files_changed:
        logger.warning("coder produced no parseable FILE blocks")

    logger.info("coder wrote %d file(s): %s", len(files_changed), [f["path"] for f in files_changed])
    return {"files_changed": files_changed, "status": "testing"}


def tester_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    result = run_command(runtime.context.driver, state["test_command"], timeout=settings.TEST_COMMAND_TIMEOUT)
    combined_output = f"$ {state['test_command']}\n{result.stdout}\n{result.stderr}".strip()
    logger.info("tester exit_code=%s", result.exit_code)

    if result.exit_code == 0:
        status = "passed"
    elif state["iteration"] >= state["max_iterations"]:
        status = "failed"
    else:
        status = "healing"

    return {
        "test_output": combined_output,
        "test_exit_code": result.exit_code,
        "status": status,
    }


def self_healer_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    iteration = state["iteration"] + 1
    revised_plan = get_completion(
        [
            {"role": "system", "content": SELF_HEALER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": SELF_HEALER_USER_TEMPLATE.format(
                    task=state["task"],
                    plan=state["plan"],
                    test_command=state["test_command"],
                    test_output=state["test_output"],
                ),
            },
        ]
    )
    logger.info("self_healer iteration=%d produced revised plan (%d chars)", iteration, len(revised_plan))
    return {
        "plan": revised_plan,
        "error_context": state["test_output"],
        "iteration": iteration,
        "status": "coding",
    }
