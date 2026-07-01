"""Tests for the header-based CSRF dependency."""

from __future__ import annotations

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.csrf import generate_csrf_token, require_csrf_header  # noqa: E402

app_test = FastAPI()


@app_test.post("/json-endpoint")
async def json_ep(_=Depends(require_csrf_header)):
    return {"ok": True}


SESSION_COOKIE = "abc123"
VALID_TOKEN = generate_csrf_token(SESSION_COOKIE)


def make_client():
    return TestClient(app_test, raise_server_exceptions=False)


@pytest.mark.core
def test_valid_header_passes():
    c = make_client()
    c.cookies.set("session_user_id", SESSION_COOKIE)
    resp = c.post(
        "/json-endpoint",
        json={},
        headers={"X-CSRF-Token": VALID_TOKEN},
    )
    assert resp.status_code == 200


@pytest.mark.core
def test_missing_header_returns_403():
    c = make_client()
    c.cookies.set("session_user_id", SESSION_COOKIE)
    resp = c.post("/json-endpoint", json={})
    assert resp.status_code == 403


@pytest.mark.core
def test_wrong_token_returns_403():
    c = make_client()
    c.cookies.set("session_user_id", SESSION_COOKIE)
    resp = c.post(
        "/json-endpoint",
        json={},
        headers={"X-CSRF-Token": "badtoken"},
    )
    assert resp.status_code == 403
