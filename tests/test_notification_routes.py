"""Tests for routes/notifications.py."""
from __future__ import annotations

import pytest

from models.notification import Notification
from models.notification_preference import NotificationPreference
from models.player import Player
from services.auth_service import create_session_cookie, create_user
from services.notification_service import create_default_preferences


@pytest.fixture()
def player_with_user(db):
    user = create_user(db, "puser", "p@test.com", "pass", role="member")
    player = Player(
        first_name="Test", last_name="Player", email="p@test.com",
        user_id=user.id, is_active=True,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    create_default_preferences(player.id, db)
    return user, player


@pytest.fixture()
def player_client(client, player_with_user):
    user, player = player_with_user
    cookie_val = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie_val)
    return client, player


def test_inbox_requires_login(client):
    r = client.get("/notifications")
    assert r.status_code in (302, 401)


def test_inbox_empty(player_client):
    c, player = player_client
    r = c.get("/notifications")
    assert r.status_code == 200
    assert b"notifications" in r.content.lower()


def test_inbox_shows_notification(db, player_client):
    c, player = player_client
    notif = Notification(player_id=player.id, title="Hi", body="Body", tag="direct")
    db.add(notif)
    db.commit()

    r = c.get("/notifications")
    assert r.status_code == 200
    assert b"Hi" in r.content


def test_mark_read(db, player_client):
    c, player = player_client
    notif = Notification(player_id=player.id, title="Hi", body="Body", tag="direct")
    db.add(notif)
    db.commit()

    r = c.post(f"/notifications/{notif.id}/read")
    assert r.status_code in (200, 302)
    db.refresh(notif)
    assert notif.is_read is True


def test_mark_read_all(db, player_client):
    c, player = player_client
    for i in range(3):
        db.add(Notification(player_id=player.id, title=f"N{i}", body="B", tag="direct"))
    db.commit()

    r = c.post("/notifications/read-all")
    assert r.status_code in (200, 302)
    unread = db.query(Notification).filter(
        Notification.player_id == player.id, Notification.is_read.is_(False)
    ).count()
    assert unread == 0


def test_cannot_mark_other_players_notification(db, player_client, admin_user):
    c, player = player_client
    other_player = Player(first_name="Other", last_name="P", is_active=True)
    db.add(other_player)
    db.commit()
    notif = Notification(player_id=other_player.id, title="Secret", body="B", tag="direct")
    db.add(notif)
    db.commit()

    r = c.post(f"/notifications/{notif.id}/read")
    assert r.status_code in (403, 404, 302)
    db.refresh(notif)
    assert notif.is_read is False


def test_vapid_public_key_endpoint(client):
    r = client.get("/notifications/vapid-public-key")
    assert r.status_code == 200
    data = r.json()
    assert "publicKey" in data


def test_notification_preferences_update(db, player_client):
    c, player = player_client
    r = c.post(
        "/notifications/preferences",
        data={"email": "off", "inapp": "on", "webpush": "off"},
    )
    assert r.status_code in (200, 302)
    email_pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "email",
    ).one()
    assert email_pref.enabled is False
