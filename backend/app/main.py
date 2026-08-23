from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Autonomous Refactor Agent", version="0.1.0")


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "llm_model": settings.LLM_MODEL_NAME,
        "sandbox_image": settings.sandbox_image,
    }
