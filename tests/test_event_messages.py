"""Tests for /events/{id}/messages routes."""

from datetime import date

import pytest

from models.event import Event
from models.event_message import EventMessage


@pytest.fixture()
def event(db):
    e = Event(title="Chat Test", event_type="training", event_date=date(2026, 4, 10))
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def test_list_messages_requires_login(client, db, event):
    r = client.get(f"/events/{event.id}/messages")
    assert r.status_code in (302, 401)


def test_list_messages_empty(admin_client, db, event):
    r = admin_client.get(f"/events/{event.id}/messages")
    assert r.status_code == 200
    assert r.json() == []


def test_list_messages_returns_both_lanes(admin_client, db, event, admin_user):
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="announcement", body="Ann 1"))
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="Disc 1"))
    db.commit()
    r = admin_client.get(f"/events/{event.id}/messages")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    lanes = {m["lane"] for m in data}
    assert lanes == {"announcement", "discussion"}


def test_post_announcement_as_admin(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "announcement", "body": "Meeting at 10am"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["lane"] == "announcement"
    assert data["body"] == "Meeting at 10am"
    assert "id" in data
    assert data["created_at"] is not None


def test_post_discussion_as_member(member_client, db, event):
    r = member_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "discussion", "body": "See you there!"},
    )
    assert r.status_code == 201
    assert r.json()["lane"] == "discussion"


def test_post_announcement_as_member_forbidden(member_client, db, event):
    r = member_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "announcement", "body": "Unauthorized"},
    )
    assert r.status_code == 403


def test_post_invalid_lane_rejected(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "other", "body": "test"},
    )
    assert r.status_code == 400


def test_post_empty_body_rejected(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "discussion", "body": "   "},
    )
    assert r.status_code == 400


def test_post_nonexistent_event(admin_client, db):
    r = admin_client.post(
        "/events/99999/messages",
        json={"lane": "discussion", "body": "Hello"},
    )
    assert r.status_code == 404


def test_delete_own_message_as_member(member_client, db, event, member_user):
    msg = EventMessage(event_id=event.id, user_id=member_user.id, lane="discussion", body="Mine")
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = member_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert db.get(EventMessage, msg.id) is None


def test_delete_others_message_as_member_forbidden(member_client, db, event, admin_user):
    msg = EventMessage(
        event_id=event.id, user_id=admin_user.id, lane="discussion", body="Admin's"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = member_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 403


def test_delete_any_message_as_admin(admin_client, db, event, member_user):
    msg = EventMessage(
        event_id=event.id, user_id=member_user.id, lane="discussion", body="Member's"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = admin_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 200
    assert db.get(EventMessage, msg.id) is None


def test_delete_nonexistent_message(admin_client, db, event):
    r = admin_client.delete(f"/events/{event.id}/messages/99999")
    assert r.status_code == 404


def test_messages_ordered_by_created_at(admin_client, db, event, admin_user):
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="First"))
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="Second"))
    db.commit()
    r = admin_client.get(f"/events/{event.id}/messages")
    data = r.json()
    assert data[0]["body"] == "First"
    assert data[1]["body"] == "Second"
