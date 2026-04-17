"""Integration tests for GET /auth/magic."""

from __future__ import annotations

from services.auth_service import create_user


def _make_token(user_id: int, path: str) -> str:
    """Create a valid magic link token directly (bypasses APP_URL check)."""
    from itsdangerous import URLSafeTimedSerializer

    import app.config
    s = URLSafeTimedSerializer(app.config.settings.SECRET_KEY, salt="magic-link")
    return s.dumps({"u": user_id, "p": path})


def test_magic_link_valid_sets_cookie_and_redirects(client, db):
    """Valid token: sets session cookie and redirects to the encoded path."""
    user = create_user(db, "ml_user", "ml@test.com", "pass123")
    token = _make_token(user.id, "/dashboard")
    resp = client.get(f"/auth/magic?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert "session_user_id" in resp.cookies


def test_magic_link_valid_event_redirect(client, db):
    """Valid token with /events/7 path redirects there."""
    user = create_user(db, "ml_user2", "ml2@test.com", "pass123")
    token = _make_token(user.id, "/events/7")
    resp = client.get(f"/auth/magic?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/events/7"


def test_magic_link_invalid_token_redirects_to_login(client):
    """Invalid token redirects to login."""
    resp = client.get("/auth/magic?token=bad.token.value", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


def test_magic_link_missing_token_redirects_to_login(client):
    """Missing token parameter redirects to login."""
    resp = client.get("/auth/magic", follow_redirects=False)
    assert resp.status_code in (302, 422)
    if resp.status_code == 302:
        assert "/auth/login" in resp.headers["location"]


def test_magic_link_unknown_user_redirects_to_login(client, db):
    """Token for non-existent user redirects to login."""
    token = _make_token(99999, "/dashboard")
    resp = client.get(f"/auth/magic?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]
