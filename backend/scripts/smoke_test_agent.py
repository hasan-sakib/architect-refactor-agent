"""Manual end-to-end smoke test for the Phase 3 LangGraph agent
(Planner -> Coder -> Tester -> SelfHealer) against a live Docker sandbox.

Seeds a tiny repo with a deliberately buggy function and a failing pytest
test, then lets the agent loop try to fix it.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/smoke_test_agent.py
"""

import shutil
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.runner import run_refactor_task
from app.core.config import get_settings
from app.drivers.base import SandboxConfig
from app.drivers.docker_driver import DockerSandboxDriver

BACKEND_DIR = Path(__file__).resolve().parents[1]
settings = get_settings()

BUGGY_SOURCE = '''def add(a, b):
    """Add two numbers."""
    return a - b  # BUG: should be a + b
'''

TEST_SOURCE = '''from calc import add


def test_add():
    assert add(2, 3) == 5
'''


def main() -> None:
    workspace = Path(tempfile.mkdtemp(prefix="refactor-agent-smoke-"))
    (workspace / "calc.py").write_text(BUGGY_SOURCE)
    (workspace / "test_calc.py").write_text(TEST_SOURCE)

    config = SandboxConfig(
        workspace_path=str(workspace),
        image=settings.sandbox_image,
        mount_path=settings.SANDBOX_WORKSPACE_MOUNT,
        mem_limit=settings.SANDBOX_MEM_LIMIT,
        nano_cpus=settings.sandbox_nano_cpus,
        network_disabled=settings.SANDBOX_NETWORK_DISABLED,
        name=f"smoke-agent-{uuid.uuid4().hex[:8]}",
    )
    driver = DockerSandboxDriver(config)

    try:
        print("[1/3] Building sandbox image and starting container...")
        driver.build(dockerfile_dir=str(BACKEND_DIR), dockerfile_name="Dockerfile.sandbox")
        driver.start()
        install = driver.exec_command("pip install --quiet pytest")
        assert install.exit_code == 0, f"failed to install pytest: {install.stderr}"

        print("[2/3] Running the agent loop (Planner -> Coder -> Tester -> SelfHealer)...")
        final_state = run_refactor_task(
            task="Fix the bug in calc.py so that add(a, b) correctly returns a + b "
                 "and the test suite passes.",
            test_command="cd /workspace && python -m pytest -q",
            driver=driver,
            max_iterations=3,
        )

        print(f"\n[3/3] Final status: {final_state['status']} (iteration {final_state['iteration']})")
        print(f"      files_changed: {[f['path'] for f in final_state['files_changed']]}")
        print(f"      test_exit_code: {final_state['test_exit_code']}")
        print("--- final calc.py ---")
        print((workspace / "calc.py").read_text())

        assert final_state["status"] == "passed", (
            f"expected status='passed', got '{final_state['status']}'\n"
            f"test_output:\n{final_state['test_output']}"
        )
        print("\nAll checks passed.")
    finally:
        driver.stop()
        driver.cleanup()
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
