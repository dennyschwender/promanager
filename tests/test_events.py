"""Tests for /events routes."""
from datetime import date
from unittest.mock import patch

from models.event import Event

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_events_list(admin_client):
    resp = admin_client.get("/events", follow_redirects=False)
    assert resp.status_code == 200


def test_events_requires_login(client):
    resp = client.get("/events", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_event(admin_client, db):
    with patch("services.attendance_service.ensure_attendance_records") as mock_ensure:
        mock_ensure.return_value = None
        resp = admin_client.post(
            "/events/new",
            data={
                "title": "Weekly Training",
                "event_type": "training",
                "event_date": "2026-03-15",
                "event_time": "18:00",
                "location": "Gym A",
                "description": "",
                "season_id": "",
                "team_id": "",
            },
            follow_redirects=False,
        )
    assert resp.status_code == 302
    event = db.query(Event).filter(Event.title == "Weekly Training").first()
    assert event is not None
    assert event.event_type == "training"


def test_create_event_missing_title(admin_client):
    resp = admin_client.post(
        "/events/new",
        data={
            "title": "",
            "event_type": "training",
            "event_date": "2026-03-15",
            "event_time": "",
            "location": "",
            "description": "",
            "season_id": "",
            "team_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_event_detail(admin_client, db):
    event = Event(title="Test Event", event_type="match", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(event)

    resp = admin_client.get(f"/events/{event.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Test Event" in resp.content


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_event(admin_client, db):
    event = Event(title="Old Title", event_type="training", event_date=date(2026, 4, 10))
    db.add(event)
    db.commit()
    db.refresh(event)

    resp = admin_client.post(
        f"/events/{event.id}/edit",
        data={
            "title": "New Title",
            "event_type": "match",
            "event_date": "2026-04-10",
            "event_time": "",
            "location": "",
            "description": "",
            "season_id": "",
            "team_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(event)
    assert event.title == "New Title"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_event(admin_client, db):
    event = Event(title="ToDelete", event_type="training", event_date=date(2026, 5, 1))
    db.add(event)
    db.commit()
    db.refresh(event)
    eid = event.id

    resp = admin_client.post(f"/events/{eid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Event, eid) is None
