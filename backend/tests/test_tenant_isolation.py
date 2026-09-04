import time
import uuid

import jwt
import pytest

from app.api import task_store
from app.api.schemas import TaskCreateRequest
from app.core.auth import TokenError
from app.core.config import get_settings
from app.core.stream_ticket import issue_stream_ticket, verify_stream_ticket


def test_reading_another_users_task_returns_404(client_as, db_session, upload_for, user_a, user_b):
    upload_b = upload_for(user_b)
    task_b = task_store.create_task(
        db_session,
        user_id=user_b.id,
        upload_id=upload_b.id,
        repo_path=upload_b.repo_path,
        req=TaskCreateRequest(task="x", test_command="true"),
    )

    resp = client_as(user_a).get(f"/api/tasks/{task_b.id}")

    assert resp.status_code == 404, "user A must not be able to read user B's task"


def test_submitting_against_another_users_upload_returns_404(client_as, upload_for, user_a, user_b):
    upload_b = upload_for(user_b)

    resp = client_as(user_a).post(
        "/api/tasks",
        json={"upload_id": str(upload_b.id), "task": "x", "test_command": "true"},
    )

    assert resp.status_code == 404, "user A must not be able to submit a task against user B's upload"


def test_stream_ticket_is_scoped_to_its_own_task(user_a):
    task_x = uuid.uuid4()
    task_y = uuid.uuid4()
    ticket, _ = issue_stream_ticket(user_id=user_a.id, task_id=task_x)

    with pytest.raises(TokenError):
        verify_stream_ticket(ticket, task_id=task_y)

    # sanity check: the same ticket against its own task must succeed
    assert verify_stream_ticket(ticket, task_id=task_x) == user_a.id


def test_expired_stream_ticket_is_rejected(user_a):
    task_id = uuid.uuid4()
    settings = get_settings()
    now = int(time.time())
    expired_token = jwt.encode(
        {"sub": str(user_a.id), "tid": str(task_id), "aud": "sse", "iat": now - 700, "exp": now - 100},
        settings.STREAM_TICKET_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(TokenError):
        verify_stream_ticket(expired_token, task_id=task_id)
