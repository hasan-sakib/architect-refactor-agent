from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Sync engine deliberately, not async: the agent executor runs the LangGraph
# loop in a worker thread (not a coroutine), so a thread-safe sync client
# that just borrows a pooled connection is simpler and safer here than
# marshalling DB calls back onto the asyncio event loop.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Short-lived session with commit/rollback — used both from FastAPI's
    get_db dependency and directly from the executor's worker thread."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session
