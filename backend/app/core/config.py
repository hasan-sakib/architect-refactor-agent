from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM abstraction (LiteLLM) ---
    LLM_MODEL_NAME: str = "ollama_chat/qwen2.5-coder"
    OLLAMA_API_BASE: str = "http://localhost:11434"
    LITELLM_API_KEY: Optional[str] = None

    # --- Sandbox (BaseSandboxDriver / DockerSandboxDriver) ---
    SANDBOX_IMAGE_NAME: str = "refactor-agent-sandbox"
    SANDBOX_IMAGE_TAG: str = "latest"
    SANDBOX_DOCKERFILE_PATH: str = "Dockerfile.sandbox"
    DOCKER_SOCKET_URL: Optional[str] = None
    SANDBOX_WORKSPACE_MOUNT: str = "/workspace"
    SANDBOX_MEM_LIMIT: str = "2g"
    SANDBOX_CPU_LIMIT: float = 2.0
    SANDBOX_NETWORK_DISABLED: bool = False

    @property
    def sandbox_image(self) -> str:
        return f"{self.SANDBOX_IMAGE_NAME}:{self.SANDBOX_IMAGE_TAG}"

    @property
    def sandbox_nano_cpus(self) -> int:
        return int(self.SANDBOX_CPU_LIMIT * 1_000_000_000)

    # --- RAG (Phase 2: Tree-sitter chunker + ChromaDB) ---
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "codebase"
    RAG_CHUNK_MAX_BYTES: int = 4000

    # --- App ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Uploads ---
    # HOST_HOME is only set when running dockerized (docker-compose injects
    # the *host's* $HOME) — inside the backend container, Path.home() would
    # otherwise resolve to /root, which the host's Docker daemon (used via
    # DooD to bind-mount into sandbox containers) has no knowledge of.
    HOST_HOME: str = ""

    @property
    def upload_root(self) -> str:
        base = self.HOST_HOME or str(Path.home())
        return str(Path(base) / ".refactor-agent-uploads")

    # --- Limits (sized for a public multi-tenant deployment, not solo use) ---
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024  # 100 MiB total per upload
    MAX_UPLOAD_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MiB per individual file
    # Starlette's multipart parser hard-caps at 1000 files per request
    # regardless of this setting (raises its own 400 first) — kept in sync
    # rather than left as an unreachable, misleadingly higher number.
    MAX_UPLOAD_FILES: int = 1000
    TEST_COMMAND_TIMEOUT: int = 240  # seconds; was hardcoded at 120, too short for cold npm ci/pip installs
    TASK_MAX_WALL_SECONDS: int = 900  # hard cap on total task duration across all self-heal iterations
    MAX_CONCURRENT_TASKS: int = 3  # bounded worker pool size for the sandbox executor
    MAX_TASKS_PER_USER: int = 1  # concurrent running tasks per user, on top of the global pool above

    # --- Upload retention ---
    # Uploads never get cleaned up otherwise. Both mechanisms run: the TTL
    # sweep is the safety net (catches uploads whose task never ran, or a
    # crash mid-run); the grace period is the common path (frees space soon
    # after a task finishes). Safe to be aggressive — diff content lives in
    # task_events/final_state, not on disk, so deleting the upload doesn't
    # break the UI for an already-finished task.
    UPLOAD_RETENTION_HOURS: int = 24
    UPLOAD_POST_TASK_GRACE_MINUTES: int = 60
    UPLOAD_SWEEP_INTERVAL_MINUTES: int = 15

    # --- Sandbox hardening ---
    SANDBOX_UID: int = 1000  # matches Dockerfile.sandbox's non-root `sandbox` user
    SANDBOX_GID: int = 1000
    SANDBOX_PIDS_LIMIT: int = 256  # fork-bomb containment
    SANDBOX_NETWORK_NAME: Optional[str] = None  # set in production to an isolated bridge (enable_icc=false)

    # --- Auth & persistence ---
    # AUTH_MODE="disabled" is the local-dev escape hatch: every request is
    # treated as a fixed synthetic user, no Supabase project needed. Never
    # valid in production — enforced by the validator below.
    AUTH_MODE: str = "disabled"  # "disabled" | "supabase"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/refactor_agent"

    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: Optional[str] = None  # legacy HS256 shared secret, if not using JWKS
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # Signs short-lived, task-scoped SSE stream tickets (EventSource can't
    # set an Authorization header). Must be set to a real random value in
    # production; the local-dev default is fine only because AUTH_MODE is
    # "disabled" there too.
    STREAM_TICKET_SECRET: str = "local-dev-insecure-stream-ticket-secret"
    STREAM_TICKET_TTL_SECONDS: int = 600

    # Local/admin escape hatch: lets the "type a host path" field work.
    # Defaults to false (safe-by-default) — the product is uploads-only;
    # opt back in explicitly via .env, and only if the mount actually covers
    # the path you want to type. Never true in production.
    ALLOW_ARBITRARY_REPO_PATH: bool = False

    @model_validator(mode="after")
    def _validate_production_auth(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.AUTH_MODE != "supabase":
                raise ValueError("AUTH_MODE must be 'supabase' when APP_ENV=production")
            if not self.SUPABASE_URL:
                raise ValueError("SUPABASE_URL must be set when APP_ENV=production")
            if self.STREAM_TICKET_SECRET == "local-dev-insecure-stream-ticket-secret":
                raise ValueError("STREAM_TICKET_SECRET must be overridden when APP_ENV=production")
            if self.ALLOW_ARBITRARY_REPO_PATH:
                raise ValueError("ALLOW_ARBITRARY_REPO_PATH must be false when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
