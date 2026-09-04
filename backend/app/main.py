from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import router as api_router
from app.api.deps import get_verifier
from app.api.task_store import reconcile_orphaned
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import session_scope

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.AUTH_MODE == "supabase":
        get_verifier().warmup()
    try:
        with session_scope() as db:
            reconcile_orphaned(db)
    except Exception:
        # A database being briefly unreachable at boot shouldn't crash the
        # whole app — /health surfaces db status so this isn't silent.
        logger.exception("failed to reconcile orphaned tasks on startup")
    yield


app = FastAPI(title="Autonomous Refactor Agent", version="0.1.0", lifespan=lifespan)

# Local dev tool: the Phase 5 React dashboard runs on Vite's default ports.
# TODO(Phase 3): make this conditional on APP_ENV != "production".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check() -> dict:
    db_status = "ok"
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_status = "degraded"
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "auth_mode": settings.AUTH_MODE,
        "db": db_status,
        "llm_model": settings.LLM_MODEL_NAME,
        "sandbox_image": settings.sandbox_image,
    }
