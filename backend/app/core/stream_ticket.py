import time
import uuid

import jwt

from app.core.auth import TokenError
from app.core.config import get_settings

settings = get_settings()

STREAM_TICKET_AUDIENCE = "sse"


def issue_stream_ticket(*, user_id: uuid.UUID, task_id: uuid.UUID) -> tuple[str, int]:
    """Short-lived, task-scoped ticket — EventSource can't set an
    Authorization header, so a normal Supabase access token can't be used
    directly for the SSE connection. Scoping to one task_id means a leaked
    ticket (query params end up in logs/Referer headers) only exposes one
    run's live output, not the user's full session."""
    now = int(time.time())
    ttl = settings.STREAM_TICKET_TTL_SECONDS
    token = jwt.encode(
        {
            "sub": str(user_id),
            "tid": str(task_id),
            "aud": STREAM_TICKET_AUDIENCE,
            "iat": now,
            "exp": now + ttl,
        },
        settings.STREAM_TICKET_SECRET,
        algorithm="HS256",
    )
    return token, ttl


def verify_stream_ticket(token: str, *, task_id: uuid.UUID) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token,
            settings.STREAM_TICKET_SECRET,
            algorithms=["HS256"],
            audience=STREAM_TICKET_AUDIENCE,
        )
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e

    if claims.get("tid") != str(task_id):
        raise TokenError("stream ticket is not valid for this task")

    try:
        return uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError, TypeError) as e:
        raise TokenError("stream ticket missing a valid subject") from e
