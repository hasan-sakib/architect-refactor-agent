import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import task_store
from app.api.deps import get_current_user
from app.core.auth import AuthenticatedUser
from app.db.session import SessionLocal


def _make_user(suffix: str) -> AuthenticatedUser:
    return AuthenticatedUser(id=uuid.uuid4(), email=f"{suffix}@test.local", claims={})


@pytest.fixture
def user_a() -> AuthenticatedUser:
    return _make_user("a")


@pytest.fixture
def user_b() -> AuthenticatedUser:
    return _make_user("b")


@pytest.fixture
def db_session():
    session = SessionLocal()
    # Both test users need an app_users row to satisfy FKs — the app upserts
    # this on every authenticated request in production; tests do it directly.
    yield session
    session.close()


@pytest.fixture
def seed_users(db_session, user_a, user_b):
    from sqlalchemy import text

    for user in (user_a, user_b):
        db_session.execute(
            text("INSERT INTO app_users (id, email) VALUES (:id, :email) ON CONFLICT (id) DO NOTHING"),
            {"id": str(user.id), "email": user.email},
        )
    db_session.commit()


@pytest.fixture
def client_as(seed_users):
    """Returns a function that builds a TestClient authenticated as the
    given user, via FastAPI's dependency_overrides (not real JWTs — this
    tests the ownership-scoping logic in routes.py/task_store.py, not the
    Supabase JWT verification itself, which is tested separately)."""
    from app.main import app

    def _client(user: AuthenticatedUser) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def upload_for(db_session):
    def _upload(user: AuthenticatedUser, repo_path: str | None = None):
        # repo_path has a unique constraint — each call needs its own path
        # unless a test deliberately wants to share one.
        repo_path = repo_path or f"/tmp/test-upload-{uuid.uuid4().hex}"
        return task_store.create_upload(db_session, user_id=user.id, repo_path=repo_path, file_count=1, total_bytes=1)

    return _upload
