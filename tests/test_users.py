"""Tests for /auth/users routes."""

from models.user import User
from services.auth_service import hash_password


def _make_user(db, username, email, role="member"):
    u = User(username=username, email=email, hashed_password=hash_password("Pass1234!"), role=role)
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


def test_cannot_deactivate_last_admin(db):
    """Cannot deactivate a user who is the only remaining active admin."""
    from fastapi.testclient import TestClient

    from app.csrf import require_csrf, require_csrf_header
    from app.database import get_db
    from app.main import app
    from routes._auth_helpers import require_admin
    from services.auth_service import create_session_cookie

    # admin_b is the only active admin; admin_a is a member acting as the requester
    admin_a = _make_user(db, "admina_last", "admina@test.com", role="member")
    admin_b = _make_user(db, "adminb_last", "adminb@test.com", role="admin")
    db.commit()

    async def _no_csrf():
        pass

    # Bypass role guard so member admin_a can reach the route
    from starlette.requests import Request as _Request

    def _fake_require_admin(request: _Request):
        return request.state.user  # noqa: E731

    app.dependency_overrides[get_db] = lambda: (yield db)
    app.dependency_overrides[require_csrf] = _no_csrf
    app.dependency_overrides[require_csrf_header] = _no_csrf
    app.dependency_overrides[require_admin] = _fake_require_admin

    cookie_val = create_session_cookie(admin_a.id)
    c = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    c.cookies.set("session_user_id", cookie_val)

    # admin_a (member) tries to deactivate admin_b (the only active admin) → last-admin guard fires
    resp = c.post(f"/auth/users/{admin_b.id}/toggle-active", data={"csrf_token": "test"})
    app.dependency_overrides.clear()
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


def test_cannot_delete_last_admin(db):
    """Cannot delete a user who is the only remaining active admin."""
    from fastapi.testclient import TestClient
    from starlette.requests import Request as _Request

    from app.csrf import require_csrf, require_csrf_header
    from app.database import get_db
    from app.main import app
    from routes._auth_helpers import require_admin
    from services.auth_service import create_session_cookie

    # admin_b is the only active admin; admin_a is a member acting as the requester
    admin_a = _make_user(db, "admina_del", "admina_del@test.com", role="member")
    admin_b = _make_user(db, "adminb_del", "adminb_del@test.com", role="admin")
    db.commit()

    async def _no_csrf():
        pass

    def _fake_require_admin(request: _Request):
        return request.state.user  # noqa: E731

    app.dependency_overrides[get_db] = lambda: (yield db)
    app.dependency_overrides[require_csrf] = _no_csrf
    app.dependency_overrides[require_csrf_header] = _no_csrf
    app.dependency_overrides[require_admin] = _fake_require_admin

    cookie_val = create_session_cookie(admin_a.id)
    c = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    c.cookies.set("session_user_id", cookie_val)

    # admin_a (member) tries to delete admin_b (the only active admin) → last-admin guard fires
    resp = c.post(f"/auth/users/{admin_b.id}/delete", data={"csrf_token": "test"})
    app.dependency_overrides.clear()
    assert resp.status_code in (400, 403)


# ---------------------------------------------------------------------------
# Bulk create — GET
# ---------------------------------------------------------------------------


def test_bulk_create_get_admin_200(admin_client):
    resp = admin_client.get("/auth/users/bulk-create", follow_redirects=False)
    assert resp.status_code == 200


def test_bulk_create_get_member_403(member_client):
    resp = member_client.get("/auth/users/bulk-create", follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_bulk_create_shows_eligible_players(admin_client, db):
    from models.player import Player

    p = Player(first_name="Frank", last_name="Test", is_active=True, email="frank@test.com")
    db.add(p)
    p2 = Player(first_name="Grace", last_name="Test", is_active=True)
    db.add(p2)
    db.commit()
    resp = admin_client.get("/auth/users/bulk-create")
    assert b"frank@test.com" in resp.content
    assert b"Grace" not in resp.content


def test_bulk_create_excludes_linked_players(admin_client, db):
    from models.player import Player

    u = _make_user(db, "henry", "henry@test.com")
    p = Player(first_name="Henry", last_name="Test", is_active=True, email="henry@test.com", user_id=u.id)
    db.add(p)
    db.commit()
    resp = admin_client.get("/auth/users/bulk-create")
    assert b"henry@test.com" not in resp.content


# ---------------------------------------------------------------------------
# Bulk create — POST
# ---------------------------------------------------------------------------


def test_bulk_create_post_creates_users(admin_client, db):
    from unittest.mock import patch

    from models.player import Player

    p = Player(first_name="Ivy", last_name="Test", is_active=True, email="ivy@test.com")
    db.add(p)
    db.commit()

    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
            follow_redirects=False,
        )
    assert resp.status_code == 200  # re-render with results
    assert b"account(s) created" in resp.content  # verify results rendered

    db.expire_all()
    p_fresh = db.get(Player, p.id)
    assert p_fresh.user_id is not None
    u = db.get(User, p_fresh.user_id)
    assert u.email == "ivy@test.com"
    assert u.role == "member"


def test_bulk_create_post_skips_already_linked(admin_client, db):
    from unittest.mock import patch

    from models.player import Player

    existing_user = _make_user(db, "jack@test.com", "jack@test.com")
    p = Player(first_name="Jack", last_name="Test", is_active=True, email="jack@test.com", user_id=existing_user.id)
    db.add(p)
    db.commit()

    count_before = db.query(User).count()
    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
        )
    assert resp.status_code == 200
    # No new user created — count unchanged
    assert db.query(User).count() == count_before


def test_bulk_create_post_skips_existing_email(admin_client, db):
    from unittest.mock import patch

    from models.player import Player

    # User with same email already exists but player not linked
    _make_user(db, "kate@test.com", "kate@test.com")
    p = Player(first_name="Kate", last_name="Test", is_active=True, email="kate@test.com")
    db.add(p)
    db.commit()

    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
        )
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(Player, p.id).user_id is None  # not linked
