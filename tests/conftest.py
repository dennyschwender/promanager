"""Shared pytest fixtures."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Must be set BEFORE any app imports ────────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.csrf import require_csrf  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from services.auth_service import create_session_cookie, create_user  # noqa: E402
import models  # noqa: E402, F401  — ensures all tables are registered on Base


# ── Single shared in-memory engine (StaticPool so all connections share it) ───
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_test_engine)


# ── Patch the app-level SessionLocal once for the whole session ────────────────
import app.database as _db_module  # noqa: E402

_TestingSessionLocal = sessionmaker(
    bind=_test_engine, autocommit=False, autoflush=False
)
_db_module.SessionLocal = _TestingSessionLocal  # AuthMiddleware uses this


@pytest.fixture(scope="function")
def db():
    """Fresh-state DB session per test — truncates all tables before each test."""
    with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        yield db

    async def override_csrf():
        pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_csrf] = override_csrf
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def csrf_client(db):
    """TestClient with CSRF enforcement enabled (no override)."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db):
    return create_user(db, "admin", "admin@test.com", "adminpass", role="admin")


@pytest.fixture()
def member_user(db):
    return create_user(db, "member1", "member@test.com", "memberpass", role="member")


@pytest.fixture()
def admin_client(client, admin_user):
    """TestClient pre-authenticated as admin."""
    cookie_val = create_session_cookie(admin_user.id)
    client.cookies.set("session_user_id", cookie_val)
    return client


@pytest.fixture()
def member_client(client, member_user):
    """TestClient pre-authenticated as member."""
    cookie_val = create_session_cookie(member_user.id)
    client.cookies.set("session_user_id", cookie_val)
    return client
