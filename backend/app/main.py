from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Autonomous Refactor Agent", version="0.1.0")

# Local dev tool: the Phase 5 React dashboard runs on Vite's default ports.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "llm_model": settings.LLM_MODEL_NAME,
        "sandbox_image": settings.sandbox_image,
    }
