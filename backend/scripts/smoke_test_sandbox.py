"""Manual smoke test for DockerSandboxDriver. Requires Docker Desktop running.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/smoke_test_sandbox.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.drivers.base import SandboxConfig
from app.drivers.docker_driver import DockerSandboxDriver

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = get_settings()
    workspace = Path(tempfile.mkdtemp(prefix="refactor-agent-smoke-"))

    config = SandboxConfig(
        workspace_path=str(workspace),
        image=settings.sandbox_image,
        mount_path=settings.SANDBOX_WORKSPACE_MOUNT,
        mem_limit=settings.SANDBOX_MEM_LIMIT,
        nano_cpus=settings.sandbox_nano_cpus,
        network_disabled=settings.SANDBOX_NETWORK_DISABLED,
    )
    driver = DockerSandboxDriver(config)

    try:
        print(f"[1/4] Building image from {BACKEND_DIR} using {settings.SANDBOX_DOCKERFILE_PATH} ...")
        tag = driver.build(str(BACKEND_DIR), settings.SANDBOX_DOCKERFILE_PATH)
        print(f"      built: {tag}")

        print("[2/4] Starting sandbox container ...")
        session_id = driver.start()
        print(f"      started: {session_id[:12]} running={driver.is_running()}")

        print("[3/4] Executing commands ...")
        result = driver.exec_command("python3 --version && echo hello-from-sandbox")
        print(f"      exit_code={result.exit_code} duration={result.duration_seconds:.2f}s")
        print(f"      stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"      stderr: {result.stderr.strip()}")
        assert result.exit_code == 0, "smoke test command failed"

        print("[4/4] Tearing down ...")
        driver.stop()
        driver.cleanup()
        print("      done. No leftover containers should remain.")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
