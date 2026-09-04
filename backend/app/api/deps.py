import time
import uuid
from functools import lru_cache
from typing import Annotated, Iterator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, SupabaseJWTVerifier, TokenError
from app.core.config import Settings, get_settings
from app.db.session import get_db as _get_db

bearer_scheme = HTTPBearer(auto_error=False)

# Fixed synthetic identity for AUTH_MODE=disabled (local/native dev, no
# Supabase project needed). Seeded into app_users by the initial migration
# so foreign keys on uploads/tasks resolve.
LOCAL_DEV_USER = AuthenticatedUser(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    email="local@dev",
    claims={},
)

_touch_cache: dict[uuid.UUID, float] = {}
_TOUCH_TTL_SECONDS = 300


@lru_cache
def get_verifier() -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(get_settings())


def get_db() -> Iterator[Session]:
    yield from _get_db()


def _touch_app_user(db: Session, user: AuthenticatedUser) -> None:
    last = _touch_cache.get(user.id)
    now = time.monotonic()
    if last is not None and now - last < _TOUCH_TTL_SECONDS:
        return
    db.execute(
        text(
            """
            INSERT INTO app_users (id, email)
            VALUES (:id, :email)
            ON CONFLICT (id) DO UPDATE SET last_seen_at = now(), email = EXCLUDED.email
            """
        ),
        {"id": str(user.id), "email": user.email},
    )
    db.commit()
    _touch_cache[user.id] = now


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Sync def, not async — a JWKS cache-miss fetch inside verify() does a
    blocking HTTP call, and FastAPI runs sync dependencies in its threadpool,
    so a key rotation can't stall the event loop for every other request."""
    if settings.AUTH_MODE == "disabled":
        return LOCAL_DEV_USER

    if creds is None:
        raise HTTPException(status_code=401, detail="missing bearer token", headers={"WWW-Authenticate": "Bearer"})

    try:
        user = get_verifier().verify(creds.credentials)
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"}) from e

    _touch_app_user(db, user)
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
