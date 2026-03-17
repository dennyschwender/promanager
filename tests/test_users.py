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


# ---------------------------------------------------------------------------
# Toggle active
# ---------------------------------------------------------------------------

def test_toggle_active_deactivates_user(admin_client, db, admin_user):
    target = _make_user(db, "bob", "bob@test.com")
    db.commit()
    resp = admin_client.post(
        f"/auth/users/{target.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(target)
    assert target.is_active is False


def test_toggle_active_reactivates_user(admin_client, db):
    target = _make_user(db, "carol", "carol@test.com")
    target.is_active = False
    db.commit()
    resp = admin_client.post(
        f"/auth/users/{target.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(target)
    assert target.is_active is True


def test_cannot_deactivate_self(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


def test_cannot_deactivate_last_admin(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_user(admin_client, db):
    target = _make_user(db, "dave", "dave@test.com")
    db.commit()
    uid = target.id
    resp = admin_client.post(
        f"/auth/users/{uid}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.get(User, uid) is None


def test_delete_user_unlinks_player(admin_client, db):
    from models.player import Player
    target = _make_user(db, "eve", "eve@test.com")
    player = Player(first_name="Eve", last_name="Test", is_active=True, user_id=target.id)
    db.add(player)
    db.commit()
    pid = player.id
    admin_client.post(f"/auth/users/{target.id}/delete", data={"csrf_token": "test"})
    db.expire_all()
    p = db.get(Player, pid)
    assert p.user_id is None


def test_cannot_delete_self(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


def test_cannot_delete_last_admin(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)
