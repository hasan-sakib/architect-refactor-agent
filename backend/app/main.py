import asyncio
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import router as api_router
from app.api.deps import get_verifier
from app.api.task_store import reconcile_orphaned
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retention import run_retention_sweep
from app.db.session import session_scope
from app.drivers.docker_driver import reap_orphaned_sandboxes

settings = get_settings()
logger = get_logger(__name__)


async def _retention_sweep_loop() -> None:
    interval = settings.UPLOAD_SWEEP_INTERVAL_MINUTES * 60
    while True:
        await asyncio.sleep(interval)
        try:
            run_retention_sweep()
        except Exception:
            logger.exception("retention sweep failed")


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

    try:
        reaped = reap_orphaned_sandboxes()
        if reaped:
            logger.warning("reaped %d orphaned sandbox container(s) on startup", reaped)
    except Exception:
        logger.exception("failed to reap orphaned sandboxes on startup")

    sweeper = asyncio.create_task(_retention_sweep_loop())
    yield
    sweeper.cancel()


app = FastAPI(title="Autonomous Refactor Agent", version="0.1.0", lifespan=lifespan)

# Local dev tool by default; a real deployment shouldn't allow arbitrary
# origins to hit an authenticated API. In production, nginx serves the SPA
# and reverse-proxies /api same-origin, so the browser never needs CORS at
# all — this middleware is purely a native-dev convenience.
if settings.APP_ENV != "production":
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

    disk_free_bytes = None
    try:
        disk_free_bytes = shutil.disk_usage(settings.upload_root).free
    except OSError:
        pass

    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "auth_mode": settings.AUTH_MODE,
        "db": db_status,
        "disk_free_bytes": disk_free_bytes,
        "llm_model": settings.LLM_MODEL_NAME,
        "sandbox_image": settings.sandbox_image,
    }
