"""Tests for /auth/users routes."""
import pytest
from models.user import User
from services.auth_service import hash_password


def _make_user(db, username, email, role="member"):
    u = User(username=username, email=email,
             hashed_password=hash_password("Pass1234!"), role=role)
    db.add(u)
    db.flush()
    return u


# ---------------------------------------------------------------------------
# User list
# ---------------------------------------------------------------------------

def test_users_list_admin_200(admin_client):
    resp = admin_client.get("/auth/users", follow_redirects=False)
    assert resp.status_code == 200


def test_users_list_member_403(member_client):
    resp = member_client.get("/auth/users", follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_users_list_shows_users(admin_client, db):
    _make_user(db, "alice", "alice@test.com", role="member")
    db.commit()
    resp = admin_client.get("/auth/users")
    assert b"alice" in resp.content
