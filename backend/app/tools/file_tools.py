import posixpath

from app.drivers.base import BaseSandboxDriver


def _resolve(driver: BaseSandboxDriver, path: str) -> str:
    """Repo-relative paths (as emitted by the Coder) must be resolved against
    the sandbox's mount point before reaching put_archive/get_archive, which
    require absolute container paths."""
    if path.startswith("/"):
        return path
    return posixpath.join(driver.config.mount_path, path)


def read_file(driver: BaseSandboxDriver, path: str) -> str:
    return driver.read_file(_resolve(driver, path)).decode("utf-8", errors="replace")


def write_file(driver: BaseSandboxDriver, path: str, content: str) -> None:
    resolved = _resolve(driver, path)
    parent = posixpath.dirname(resolved)
    if parent:
        driver.exec_command(f"mkdir -p {parent}")
    driver.write_file(resolved, content)
