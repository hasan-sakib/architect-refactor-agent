from __future__ import annotations

import io
import os
import shlex
import tarfile
import time
import uuid
from typing import Optional

import docker
from docker.errors import APIError, BuildError, ImageNotFound

from app.core.config import get_settings
from app.drivers.base import (
    BaseSandboxDriver,
    ExecResult,
    SandboxBuildError,
    SandboxConfig,
    SandboxExecError,
    SandboxStartError,
)

settings = get_settings()


class DockerSandboxDriver(BaseSandboxDriver):
    """BaseSandboxDriver implementation backed by the local Docker Engine."""

    def __init__(self, config: SandboxConfig, docker_client: Optional[docker.DockerClient] = None):
        super().__init__(config)
        if docker_client is not None:
            self._client = docker_client
        elif settings.DOCKER_SOCKET_URL:
            self._client = docker.DockerClient(base_url=settings.DOCKER_SOCKET_URL)
        else:
            self._client = docker.from_env()
        self._container = None

    def build(self, dockerfile_dir: str, dockerfile_name: str = "Dockerfile.sandbox") -> str:
        try:
            image, _logs = self._client.images.build(
                path=dockerfile_dir,
                dockerfile=dockerfile_name,
                tag=self.config.image,
                rm=True,
            )
            return image.tags[0] if image.tags else self.config.image
        except (BuildError, APIError) as e:
            raise SandboxBuildError(str(e)) from e

    def start(self) -> str:
        name = self.config.name or f"sandbox-{uuid.uuid4().hex[:10]}"
        run_kwargs: dict = dict(
            image=self.config.image,
            command=["sleep", "infinity"],
            detach=True,
            name=name,
            volumes={self.config.workspace_path: {"bind": self.config.mount_path, "mode": "rw"}},
            working_dir=self.config.mount_path,
            mem_limit=self.config.mem_limit,
            nano_cpus=self.config.nano_cpus,
            environment=self.config.environment,
            labels={**self.config.labels, "refactor-agent.managed": "true"},
        )
        if self.config.memswap_limit:
            run_kwargs["memswap_limit"] = self.config.memswap_limit
        if self.config.pids_limit is not None:
            run_kwargs["pids_limit"] = self.config.pids_limit
        if self.config.user:
            run_kwargs["user"] = self.config.user
        if self.config.cap_drop:
            run_kwargs["cap_drop"] = self.config.cap_drop
        if self.config.cap_add:
            run_kwargs["cap_add"] = self.config.cap_add
        if self.config.security_opt:
            run_kwargs["security_opt"] = self.config.security_opt
        if self.config.tmpfs:
            run_kwargs["tmpfs"] = self.config.tmpfs
        # Mutually exclusive in the Docker API — a named network implies
        # network access, so it can't also be network_disabled.
        if self.config.network_disabled:
            run_kwargs["network_disabled"] = True
        elif self.config.network:
            run_kwargs["network"] = self.config.network

        try:
            self._container = self._client.containers.run(**run_kwargs)
            return self._container.id
        except (APIError, ImageNotFound) as e:
            raise SandboxStartError(str(e)) from e

    def stop(self, timeout: int = 10) -> None:
        if self._container:
            self._container.stop(timeout=timeout)

    def cleanup(self, remove_image: bool = False) -> None:
        if self._container:
            self._container.remove(force=True)
            self._container = None
        if remove_image:
            self._client.images.remove(self.config.image, force=True)

    def is_running(self) -> bool:
        if not self._container:
            return False
        self._container.reload()
        return self._container.status == "running"

    def exec_command(
        self,
        command: str,
        workdir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> ExecResult:
        if not self._container:
            raise SandboxExecError("Sandbox is not running; call start() first.")
        wrapped = f"timeout {timeout} bash -c {shlex.quote(command)}" if timeout else command
        started = time.monotonic()
        try:
            exit_code, (stdout, stderr) = self._container.exec_run(
                cmd=["bash", "-lc", wrapped],
                workdir=workdir or self.config.mount_path,
                environment=env,
                demux=True,
            )
        except APIError as e:
            raise SandboxExecError(str(e)) from e
        duration = time.monotonic() - started
        return ExecResult(
            command=command,
            exit_code=exit_code,
            stdout=(stdout or b"").decode(errors="replace"),
            stderr=(stderr or b"").decode(errors="replace"),
            duration_seconds=duration,
            timed_out=bool(timeout) and exit_code == 124,
        )

    def write_file(self, path: str, content: bytes | str) -> None:
        if not self._container:
            raise SandboxExecError("Sandbox is not running; call start() first.")
        if isinstance(content, str):
            content = content.encode()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=os.path.basename(path))
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        buf.seek(0)
        self._container.put_archive(os.path.dirname(path) or "/", buf)

    def read_file(self, path: str) -> bytes:
        if not self._container:
            raise SandboxExecError("Sandbox is not running; call start() first.")
        stream, _stat = self._container.get_archive(path)
        buf = io.BytesIO()
        for chunk in stream:
            buf.write(chunk)
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tar:
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            return f.read() if f else b""

    def get_logs(self, tail: Optional[int] = None) -> str:
        if not self._container:
            return ""
        return self._container.logs(tail=tail or "all").decode(errors="replace")


def reap_orphaned_sandboxes() -> int:
    """If the backend restarts mid-task (crash, redeploy), its sandbox
    containers leak and hold memory/CPU forever — find and remove them via
    the label every sandbox container gets in start(). Called once from the
    FastAPI lifespan on startup."""
    client = docker.from_env()
    orphans = client.containers.list(all=True, filters={"label": "refactor-agent.managed=true"})
    for container in orphans:
        try:
            container.remove(force=True)
        except APIError:
            pass
    return len(orphans)
