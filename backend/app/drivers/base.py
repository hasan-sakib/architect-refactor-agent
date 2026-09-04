from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


@dataclass
class SandboxConfig:
    workspace_path: str
    image: str = "refactor-agent-sandbox:latest"
    mount_path: str = "/workspace"
    mem_limit: str = "2g"
    # Without an explicit swap limit equal to mem_limit, Docker silently
    # allows the container to use up to 2x mem_limit via swap.
    memswap_limit: Optional[str] = None
    nano_cpus: Optional[int] = None
    pids_limit: Optional[int] = None  # fork-bomb containment
    network_disabled: bool = False
    network: Optional[str] = None  # isolated bridge name; mutually exclusive with network_disabled
    user: Optional[str] = None  # e.g. "1000:1000" — explicit non-root
    cap_drop: list[str] = field(default_factory=list)
    cap_add: list[str] = field(default_factory=list)
    security_opt: list[str] = field(default_factory=list)
    tmpfs: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    name: Optional[str] = None


class SandboxError(RuntimeError):
    pass


class SandboxBuildError(SandboxError):
    pass


class SandboxStartError(SandboxError):
    pass


class SandboxExecError(SandboxError):
    pass


class BaseSandboxDriver(abc.ABC):
    """Abstract lifecycle + execution contract for an isolated code sandbox.
    Agent tools (Phase 3) and API routes (Phase 4) depend ONLY on this class —
    never on `docker` or any other backend SDK directly."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    @abc.abstractmethod
    def build(self, dockerfile_dir: str, dockerfile_name: str = "Dockerfile.sandbox") -> str:
        """Build (or ensure existence of) the sandbox base image. Returns the image tag."""

    @abc.abstractmethod
    def start(self) -> str:
        """Start a fresh sandbox bound to config.workspace_path. Returns an opaque session id."""

    @abc.abstractmethod
    def stop(self, timeout: int = 10) -> None:
        """Stop the running sandbox."""

    @abc.abstractmethod
    def cleanup(self, remove_image: bool = False) -> None:
        """Clean up resources. Optionally remove the image."""

    @abc.abstractmethod
    def is_running(self) -> bool:
        """Check if the sandbox container is currently running."""

    @abc.abstractmethod
    def exec_command(
        self,
        command: str,
        workdir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> ExecResult:
        """Execute a command in the sandbox. Returns full result with stdout/stderr/exit code."""

    @abc.abstractmethod
    def write_file(self, path: str, content: bytes | str) -> None:
        """Write content to a file inside the sandbox."""

    @abc.abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read file content from inside the sandbox."""

    @abc.abstractmethod
    def get_logs(self, tail: Optional[int] = None) -> str:
        """Get container logs, optionally limiting to the last N lines."""

    def __enter__(self) -> BaseSandboxDriver:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.stop()
        finally:
            self.cleanup()
