# tests/test_calendar.py
from datetime import date, time

from models.event import Event
from services.calendar_service import build_ical_feed, fold_line, generate_token

# ── token ────────────────────────────────────────────────────────────────────

def test_generate_token_length():
    token = generate_token()
    assert len(token) == 64


def test_generate_token_unique():
    assert generate_token() != generate_token()


# ── fold_line ────────────────────────────────────────────────────────────────

def test_fold_line_short():
    assert fold_line("SHORT:value") == "SHORT:value"


def test_fold_line_long():
    long_line = "SUMMARY:" + "A" * 80
    folded = fold_line(long_line)
    lines = folded.split("\r\n")
    assert all(len(ln) <= 75 for ln in lines)
    assert lines[1].startswith(" ")


# ── build_ical_feed ──────────────────────────────────────────────────────────

def test_ical_basic_event(db, admin_user):
    event = Event(
        title="Training",
        event_type="training",
        event_date=date(2026, 6, 1),
        event_time=time(18, 30),
        event_end_time=time(20, 0),
        location="Sports Center",
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert "BEGIN:VCALENDAR" in result
    assert "END:VCALENDAR" in result
    assert f"UID:{event.id}@promanager" in result
    assert "SUMMARY:Training" in result
    assert "DTSTART;TZID=UTC:20260601T183000" in result
    assert "DTEND;TZID=UTC:20260601T200000" in result
    assert "LOCATION:Sports Center" in result


def test_ical_all_day_event(db, admin_user):
    event = Event(
        title="Team Day",
        event_type="other",
        event_date=date(2026, 7, 4),
        event_time=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert "DTSTART;VALUE=DATE:20260704" in result
    assert "DTEND;VALUE=DATE:20260705" in result


def test_ical_end_time_fallback(db, admin_user):
    """When event_end_time is None, DTEND = DTSTART + 1 hour."""
    event = Event(
        title="Quick Meet",
        event_type="training",
        event_date=date(2026, 6, 10),
        event_time=time(19, 0),
        event_end_time=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert "DTSTART;TZID=UTC:20260610T190000" in result
    assert "DTEND;TZID=UTC:20260610T200000" in result


def test_ical_meeting_vevent(db, admin_user):
    """meeting_time generates a second VEVENT for the meeting point."""
    event = Event(
        title="Match",
        event_type="match",
        event_date=date(2026, 6, 15),
        event_time=time(20, 0),
        event_end_time=time(22, 0),
        location="Stadium",
        meeting_time=time(19, 15),
        meeting_location="Main Parking",
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert f"UID:{event.id}-meet@promanager" in result
    assert "SUMMARY:Meet: Match" in result
    assert "DTSTART;TZID=UTC:20260615T191500" in result
    assert "DTEND;TZID=UTC:20260615T200000" in result
    assert "LOCATION:Main Parking" in result


def test_ical_meeting_falls_back_to_location(db, admin_user):
    """meeting_time with no meeting_location falls back to event location."""
    event = Event(
        title="Training",
        event_type="training",
        event_date=date(2026, 6, 20),
        event_time=time(18, 0),
        event_end_time=time(20, 0),
        location="Field B",
        meeting_time=time(17, 45),
        meeting_location=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    meet_block_start = result.find("UID:" + str(event.id) + "-meet@promanager")
    meet_block = result[meet_block_start:result.find("END:VEVENT", meet_block_start)]
    assert "LOCATION:Field B" in meet_block


def test_ical_window(db, admin_user):
    """Events older than 30 days are excluded."""
    from datetime import datetime, timedelta, timezone

    old_event = Event(
        title="Old Event",
        event_type="training",
        event_date=(datetime.now(timezone.utc).date() - timedelta(days=40)),
    )
    recent_event = Event(
        title="Recent Event",
        event_type="training",
        event_date=(datetime.now(timezone.utc).date() - timedelta(days=5)),
    )
    db.add_all([old_event, recent_event])
    db.commit()

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert "SUMMARY:Old Event" not in result
    assert "SUMMARY:Recent Event" in result


# ── endpoint tests ────────────────────────────────────────────────────────────

def test_feed_unknown_token(client):
    resp = client.get("/calendar/unknowntoken123/feed.ics", follow_redirects=False)
    assert resp.status_code == 404


def test_feed_returns_ical(db, admin_user, admin_client):
    from services.calendar_service import generate_token
    token = generate_token()
    admin_user.calendar_token = token
    db.commit()

    resp = admin_client.get(f"/calendar/{token}/feed.ics", follow_redirects=False)
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]
    assert "BEGIN:VCALENDAR" in resp.text


def test_feed_no_login_required(db, client, admin_user):
    """Feed accessible without session cookie."""
    from services.calendar_service import generate_token
    token = generate_token()
    admin_user.calendar_token = token
    db.commit()

    resp = client.get(f"/calendar/{token}/feed.ics", follow_redirects=False)
    assert resp.status_code == 200


def test_regenerate_token_requires_login(client):
    resp = client.post("/calendar/regenerate-token", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


def test_regenerate_token_changes_token(db, admin_user, admin_client):
    from services.calendar_service import generate_token
    old_token = generate_token()
    admin_user.calendar_token = old_token
    db.commit()

    resp = admin_client.post("/calendar/regenerate-token", follow_redirects=False)
    assert resp.status_code == 302

    db.refresh(admin_user)
    assert admin_user.calendar_token != old_token
    assert admin_user.calendar_token is not None


def test_old_token_returns_404_after_regenerate(db, admin_user, admin_client, client):
    from services.calendar_service import generate_token
    old_token = generate_token()
    admin_user.calendar_token = old_token
    db.commit()

    admin_client.post("/calendar/regenerate-token", follow_redirects=False)

    resp = client.get(f"/calendar/{old_token}/feed.ics", follow_redirects=False)
    assert resp.status_code == 404


def test_ical_text_escaping(db, admin_user):
    """Commas and semicolons in title/location are escaped per RFC 5545."""
    event = Event(
        title="Training, Field A; bring water",
        event_type="training",
        event_date=date(2026, 6, 1),
        event_time=time(18, 0),
        location="Gym, Building B; entrance C",
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    result = build_ical_feed(admin_user, db, "http://localhost:7000", "UTC")

    assert r"SUMMARY:Training\, Field A\; bring water" in result
    assert r"LOCATION:Gym\, Building B\; entrance C" in result
