"""Tests for /attendance routes and attendance_service."""

from datetime import date

from models.attendance import Attendance
from models.event import Event
from models.player import Player
from services.attendance_service import (
    get_event_attendance_summary,
    set_attendance,
)
from services.auth_service import create_session_cookie, create_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(db, title="Test Event", event_date=date(2026, 3, 20)):
    event = Event(title=title, event_type="training", event_date=event_date)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_player(db, first="Player", last="One"):
    player = Player(first_name=first, last_name=last, is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


# ---------------------------------------------------------------------------
# Attendance page (GET)
# ---------------------------------------------------------------------------


def test_mark_attendance_page(admin_client, db):
    event = _make_event(db)
    resp = admin_client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 200


def test_mark_attendance_redirects_for_missing_event(admin_client):
    resp = admin_client.get("/attendance/99999", follow_redirects=False)
    assert resp.status_code == 302


def test_attendance_requires_login(client, db):
    event = _make_event(db, title="Auth Test Event")
    resp = client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Set attendance (POST)
# ---------------------------------------------------------------------------


def test_set_attendance_present(admin_client, db):
    event = _make_event(db, title="Present Event")
    player = _make_player(db, "Alice", "Present")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "present", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.status == "present"


def test_set_attendance_absent(admin_client, db):
    event = _make_event(db, title="Absent Event")
    player = _make_player(db, "Bob", "Absent")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "absent", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.status == "absent"


def test_set_attendance_with_note(admin_client, db):
    event = _make_event(db, title="Note Event")
    player = _make_player(db, "Carol", "Note")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "maybe", "note": "Out of town"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.status == "maybe"
    assert att.note == "Out of town"


# ---------------------------------------------------------------------------
# Service-level summary
# ---------------------------------------------------------------------------


def test_attendance_summary(db):
    event = _make_event(db, title="Summary Event")

    p1 = _make_player(db, "Sam", "Present")
    p2 = _make_player(db, "Terry", "Absent")
    p3 = _make_player(db, "Jordan", "Maybe")

    set_attendance(db, event.id, p1.id, "present")
    set_attendance(db, event.id, p2.id, "absent")
    set_attendance(db, event.id, p3.id, "maybe")

    summary = get_event_attendance_summary(db, event.id)

    assert len(summary["present"]) == 1
    assert len(summary["absent"]) == 1
    assert len(summary["maybe"]) == 1
    assert len(summary["unknown"]) == 0
    assert summary["present"][0].first_name == "Sam"


# ---------------------------------------------------------------------------
# Member authorization boundary
# ---------------------------------------------------------------------------


def test_member_cannot_update_another_members_player(client, db):
    """A member may only update attendance for their own players."""
    # Create two members
    user_a = create_user(db, "member_a", "a@test.com", "password1", role="member")
    user_b = create_user(db, "member_b", "b@test.com", "password2", role="member")

    event = _make_event(db, title="Auth Boundary Event")

    # Player owned by user_b
    player_b = Player(first_name="Player", last_name="B", is_active=True, user_id=user_b.id)
    db.add(player_b)
    db.commit()
    db.refresh(player_b)

    # Authenticate as user_a
    client.cookies.set("session_user_id", create_session_cookie(user_a.id))

    resp = client.post(
        f"/attendance/{event.id}/{player_b.id}",
        data={"status": "present", "note": ""},
        follow_redirects=False,
    )
    # Must be redirected away — not allowed to update another user's player
    assert resp.status_code == 302
    assert f"/attendance/{event.id}" in resp.headers["location"]

    # Attendance must not have been changed to 'present'
    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player_b.id).first()
    assert att is None or att.status != "present"


def test_ensure_attendance_only_includes_season_players(db):
    """ensure_attendance_records only creates rows for players in event's (team, season)."""
    from datetime import date

    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team
    from services.attendance_service import ensure_attendance_records

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    p1 = _make_player(db, "InSeason", "Two")
    p2 = _make_player(db, "InSeason", "One")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    event = Event(
        title="S2 Match",
        event_type="match",
        event_date=date(2026, 1, 10),
        team_id=team.id,
        season_id=s2.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    ensure_attendance_records(db, event)

    from models.attendance import Attendance

    att_player_ids = {a.player_id for a in db.query(Attendance).filter(Attendance.event_id == event.id).all()}
    assert p2.id in att_player_ids  # in s2 — should be included
    assert p1.id not in att_player_ids  # in s1 — should NOT be included


def test_ensure_attendance_no_season_creates_no_records(db):
    """ensure_attendance_records with event.season_id=None creates no attendance rows."""
    from datetime import date

    from models.team import Team
    from services.attendance_service import ensure_attendance_records

    team = Team(name="NoSeason")
    db.add(team)
    db.flush()

    _make_player(db, "NoSeason", "Player")
    db.commit()

    event = Event(
        title="No Season Event",
        event_type="training",
        event_date=date(2026, 2, 1),
        team_id=team.id,
        season_id=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    ensure_attendance_records(db, event)

    from models.attendance import Attendance

    count = db.query(Attendance).filter(Attendance.event_id == event.id).count()
    assert count == 0


def test_update_attendance_json_response(admin_client, db):
    """POST with Accept: application/json returns JSON success response."""
    event = _make_event(db, title="JSON Test Event")
    player = _make_player(db, "Json", "Player")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "present", "note": "via ajax"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "present"
    assert body["note"] == "via ajax"


def test_update_attendance_json_invalid_status(admin_client, db):
    """POST with invalid status + Accept header returns ok=false."""
    event = _make_event(db, title="Invalid Status Event")
    player = _make_player(db, "Bad", "Status")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "flying", "note": ""},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "invalid_status"


def test_update_attendance_form_redirect_unchanged(admin_client, db):
    """POST without Accept: application/json still redirects (regression guard)."""
    event = _make_event(db, title="Redirect Guard Event")
    player = _make_player(db, "Redirect", "Guard")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "absent", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert f"/attendance/{event.id}" in resp.headers["location"]


def test_get_event_attendance_detail_includes_notes(db):
    """get_event_attendance_detail returns player + note per bucket."""
    from services.attendance_service import get_event_attendance_detail

    event = _make_event(db, title="Detail Test")
    p1 = _make_player(db, "Alice", "Detail")
    set_attendance(db, event.id, p1.id, "present", note="On time")

    detail = get_event_attendance_detail(db, event.id)

    assert len(detail["present"]) == 1
    entry = detail["present"][0]
    assert entry["player"].first_name == "Alice"
    assert entry["note"] == "On time"
    assert len(detail["absent"]) == 0
    assert len(detail["unknown"]) == 0
