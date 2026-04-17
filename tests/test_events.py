"""Tests for /events routes."""

import uuid
from datetime import date, timedelta
from unittest.mock import patch

from models.event import Event
from models.team import Team

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_events_list(admin_client):
    resp = admin_client.get("/events", follow_redirects=False)
    assert resp.status_code == 200


def test_events_public(client):
    resp = client.get("/events", follow_redirects=False)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_event(admin_client, db):
    team = Team(name="Test Team")
    db.add(team)
    db.commit()
    db.refresh(team)
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
                "team_id": str(team.id),
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


# ---------------------------------------------------------------------------
# Recurrence-aware deletion
# ---------------------------------------------------------------------------


def _make_recurring_events(db, count=3, start_days_ago=7):
    """Create `count` events sharing a recurrence_group_id.

    The first event is `start_days_ago` days in the past; subsequent events
    are 7 days apart (weekly). Returns list of Event objects sorted by date.
    """
    group_id = str(uuid.uuid4())
    events = []
    for i in range(count):
        ev = Event(
            title=f"Recurring {i}",
            event_type="training",
            event_date=date.today() - timedelta(days=start_days_ago) + timedelta(weeks=i),
            recurrence_group_id=group_id,
            recurrence_rule="weekly",
        )
        db.add(ev)
        events.append(ev)
    db.commit()
    for ev in events:
        db.refresh(ev)
    return events


def test_event_delete_single_leaves_series_intact(admin_client, db):
    """scope=single deletes only the targeted event; other series events survive."""
    evs = _make_recurring_events(db, count=3, start_days_ago=14)
    target = evs[0]  # past event
    sibling = evs[1]

    resp = admin_client.post(
        f"/events/{target.id}/delete",
        data={"scope": "single"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    assert db.get(Event, target.id) is None
    assert db.get(Event, sibling.id) is not None


def test_event_delete_future_removes_current_and_future(admin_client, db):
    """scope=future deletes the current event and all future events in the series,
    but leaves past events untouched."""
    # evs[0] is 7 days ago (past), evs[1] is today, evs[2] is 7 days from now
    evs = _make_recurring_events(db, count=3, start_days_ago=7)
    past_ev = evs[0]
    today_ev = evs[1]
    future_ev = evs[2]

    resp = admin_client.post(
        f"/events/{today_ev.id}/delete",
        data={"scope": "future"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    assert db.get(Event, past_ev.id) is not None  # past — untouched
    assert db.get(Event, today_ev.id) is None  # today — deleted
    assert db.get(Event, future_ev.id) is None  # future — deleted


def test_event_delete_future_on_nonrecurring_falls_back_to_single(admin_client, db):
    """scope=future on a non-recurring event silently deletes only that event."""
    ev = Event(title="Solo", event_type="training", event_date=date.today())
    db.add(ev)
    db.commit()
    db.refresh(ev)

    resp = admin_client.post(
        f"/events/{ev.id}/delete",
        data={"scope": "future"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.get(Event, ev.id) is None


def test_event_detail_includes_att_by_player(admin_client, db):
    """GET /events/{id} returns 200 and the route now provides att_by_player context."""
    from models.attendance import Attendance
    from models.player import Player

    event = Event(title="Context Test", event_type="training", event_date=date.today())
    db.add(event)
    db.commit()
    db.refresh(event)

    player = Player(first_name="Test", last_name="Player", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()

    resp = admin_client.get(f"/events/{event.id}", follow_redirects=False)
    assert resp.status_code == 200


def test_member_can_edit_own_player_from_detail(client, db):
    """A member POSTing attendance for their own player redirects to /events/{id}."""
    from models.attendance import Attendance
    from models.player import Player
    from services.auth_service import create_session_cookie, create_user

    member = create_user(db, "member_detail", "detail@test.com", "password1", role="member", must_change_password=False)
    event = Event(title="Member Edit Event", event_type="training", event_date=date.today())
    db.add(event)
    db.commit()
    db.refresh(event)

    player = Player(first_name="Own", last_name="Player", is_active=True, user_id=member.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    db.add(Attendance(event_id=event.id, player_id=player.id, status="unknown"))
    db.commit()

    client.cookies.set("session_user_id", create_session_cookie(member.id))
    resp = client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "present", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert f"/events/{event.id}" in resp.headers["location"]

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.status == "present"


# ---------------------------------------------------------------------------
# Attendance text endpoint
# ---------------------------------------------------------------------------


def test_attendance_text_returns_plain_text(admin_client, db):
    from datetime import date
    from datetime import time as dtime

    from models.attendance import Attendance
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    team = Team(name="TextTeam")
    season = Season(name="S1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Copy Test Match",
        event_type="match",
        event_date=date(2026, 4, 16),
        event_time=dtime(19, 30),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Zeno", last_name="Boscolo")
    db.add(player)
    db.commit()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="forward"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.get(f"/events/{event.id}/attendance-text?grouped=1")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "Copy Test Match" in body
    assert "Zeno Boscolo" in body
    assert "Forwards (1)" in body


def test_attendance_text_flat(admin_client, db):
    from datetime import date

    from models.attendance import Attendance
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    team = Team(name="FlatTeam")
    season = Season(name="S2", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Flat Test",
        event_type="training",
        event_date=date(2026, 4, 17),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Anna", last_name="Z")
    db.add(player)
    db.commit()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="defender"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.get(f"/events/{event.id}/attendance-text?grouped=0")
    assert resp.status_code == 200
    body = resp.text
    assert "Anna Z" in body
    assert "Defenders" not in body  # no position headers in flat mode


def test_attendance_text_404(admin_client):
    resp = admin_client.get("/events/99999/attendance-text?grouped=1")
    assert resp.status_code == 404


def test_attendance_text_requires_login(client):
    resp = client.get("/events/1/attendance-text?grouped=1", follow_redirects=False)
    assert resp.status_code == 302
