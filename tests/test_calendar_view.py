"""tests/test_calendar_view.py — Calendar month grid tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from models.event import Event


@pytest.fixture
def make_event(db):
    """Factory fixture — creates an Event and returns it."""

    def _make(
        title="Test Event",
        event_date="2026-06-15",
        event_time="18:30",
        event_type="training",
        team_id=None,
        season_id=None,
        location=None,
        meeting_time=None,
    ):
        ev = Event(
            title=title,
            event_type=event_type,
            event_date=datetime.strptime(event_date, "%Y-%m-%d").date(),
            event_time=datetime.strptime(event_time, "%H:%M").time() if event_time else None,
            location=location,
            meeting_time=datetime.strptime(meeting_time, "%H:%M").time() if meeting_time else None,
            team_id=team_id,
            season_id=season_id,
        )
        db.add(ev)
        db.commit()
        return ev

    return _make


# ── Calendar page ──


def test_calendar_page_returns_200(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_public(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_with_events(admin_client, db, make_event):
    event = make_event(event_date="2026-06-15")
    response = admin_client.get("/events/calendar?year=2026&month=6")
    assert response.status_code == 200
    assert event.title.encode() in response.content


def test_calendar_empty_month(client):
    response = client.get("/events/calendar?year=2026&month=1")
    assert response.status_code == 200


def test_calendar_month_navigation(client):
    response = client.get("/events/calendar?year=2026&month=7")
    assert response.status_code == 200


def test_calendar_invalid_month_clamps(client):
    response = client.get("/events/calendar?year=2026&month=13")
    assert response.status_code == 200


# ── Day detail API ──


def test_calendar_day_api_returns_events(admin_client, db, make_event):
    ev = make_event(event_date="2026-06-15")
    response = admin_client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert ev.title in response.text


def test_calendar_day_api_no_events(client):
    response = client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert "Nessun evento in questa data." in response.text


def test_calendar_day_api_invalid_date(client):
    response = client.get("/api/events/calendar-day?date_str=not-a-date")
    assert response.status_code == 400


def test_calendar_day_api_returns_events_en_locale(client):
    """Override locale to English for explicit string check."""
    from starlette.testclient import TestClient as _TC

    from app.main import app as _app

    c = _TC(_app, raise_server_exceptions=False, follow_redirects=False)
    c.cookies.set("locale", "en")
    response = c.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert "No events on this date." in response.text


# ── Export CSV ──


def test_events_export_returns_csv(client):
    response = client.get("/events/export?date_from=2026-06-01&date_to=2026-06-30")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "text/csv" in response.headers["content-type"]


def test_events_export_invalid_date(client):
    response = client.get("/events/export?date_from=not-a-date&date_to=2026-06-30")
    assert response.status_code == 400


def test_events_export_contains_events(admin_client, db, make_event):
    ev = make_event(title="Export Test Event", event_date="2026-06-15", event_time="18:30")
    response = admin_client.get("/events/export?date_from=2026-06-01&date_to=2026-06-30")
    assert response.status_code == 200
    assert ev.title in response.text
    assert "18:30" in response.text


def test_events_export_filename(admin_client, db, make_event):
    make_event(event_date="2026-06-15")
    response = admin_client.get("/events/export?date_from=2026-06-01&date_to=2026-06-30")
    assert response.status_code == 200
    assert 'filename="events_2026-06-01_to_2026-06-30.csv"' in response.headers.get("content-disposition", "")


def test_events_export_text_returns_events(admin_client, db, make_event):
    ev = make_event(title="Clipboard Event", event_date="2026-06-15", event_time="20:00")
    response = admin_client.get("/api/events/export-text?date_from=2026-06-01&date_to=2026-06-30")
    assert response.status_code == 200
    assert ev.title in response.text
    assert "20:00" in response.text


def test_events_export_text_no_events(client):
    response = client.get("/api/events/export-text?date_from=2026-06-01&date_to=2026-06-30")
    assert response.status_code == 200
