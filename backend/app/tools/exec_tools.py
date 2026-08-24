from typing import Optional

from app.drivers.base import BaseSandboxDriver, ExecResult


def run_command(driver: BaseSandboxDriver, command: str, timeout: Optional[int] = None) -> ExecResult:
    return driver.exec_command(command, timeout=timeout)
