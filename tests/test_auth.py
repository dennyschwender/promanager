"""Tests for /auth routes."""

from services.auth_service import create_user

# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------


def test_login_page_renders(client):
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200


def test_login_success(client, member_user):
    resp = client.post(
        "/auth/login",
        data={"username": "member1", "password": "memberpass"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert "session_user_id" in resp.cookies


def test_login_wrong_password(client, member_user):
    resp = client.post(
        "/auth/login",
        data={"username": "member1", "password": "wrongpassword"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post(
        "/auth/login",
        data={"username": "nobody", "password": "doesntmatter"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout(admin_client):
    resp = admin_client.get("/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]
    # Cookie should be cleared (set to empty or deleted)
    assert resp.cookies.get("session_user_id", "") == ""


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


def test_register_requires_admin(member_client):
    """Non-admin users must not reach the register page."""
    resp = member_client.get("/auth/register", follow_redirects=False)
    # Returns 403 (admin guard) because member is logged in but not admin
    assert resp.status_code == 403


def test_register_requires_login(client):
    """Unauthenticated users are redirected to login."""
    resp = client.get("/auth/register", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


def test_register_creates_user(admin_client):
    resp = admin_client.post(
        "/auth/register",
        data={
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "newpassword1",
            "role": "member",
        },
        follow_redirects=False,
    )
    # Success renders the register page with a flash message (200)
    assert resp.status_code == 200
    assert b"newuser" in resp.content


def test_duplicate_username_rejected(admin_client, db):
    # Pre-create the user with the same username
    create_user(db, "dupuser", "dup@test.com", "password123", role="member")

    resp = admin_client.post(
        "/auth/register",
        data={
            "username": "dupuser",
            "email": "other@test.com",
            "password": "password123",
            "role": "member",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert b"dupuser" in resp.content


def test_password_too_short_rejected(admin_client):
    """7-character password must be rejected with 400."""
    resp = admin_client.post(
        "/auth/register",
        data={
            "username": "shortpass",
            "email": "shortpass@test.com",
            "password": "1234567",  # exactly 7 chars
            "role": "member",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert b"8 characters" in resp.content


def test_password_minimum_length_accepted(admin_client):
    """8-character password must be accepted."""
    resp = admin_client.post(
        "/auth/register",
        data={
            "username": "okpassuser",
            "email": "okpass@test.com",
            "password": "12345678",  # exactly 8 chars
            "role": "member",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert b"okpassuser" in resp.content


# ---------------------------------------------------------------------------
# CSRF enforcement
# ---------------------------------------------------------------------------


def test_login_post_without_csrf_token_rejected(csrf_client):
    """POST to /auth/login without a CSRF token must return 403."""
    resp = csrf_client.post(
        "/auth/login",
        data={"username": "anyone", "password": "anything"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_login_post_with_valid_csrf_token_proceeds(csrf_client, member_user):
    """POST to /auth/login with a correct CSRF token must not be blocked by CSRF."""
    from app.csrf import generate_csrf_token

    # Build a valid CSRF token (no session cookie yet on the login page)
    token = generate_csrf_token("")
    resp = csrf_client.post(
        "/auth/login",
        data={"username": "member1", "password": "memberpass", "csrf_token": token},
        follow_redirects=False,
    )
    # CSRF passed — auth logic runs (correct creds → 302)
    assert resp.status_code == 302
