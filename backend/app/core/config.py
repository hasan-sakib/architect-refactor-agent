from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
