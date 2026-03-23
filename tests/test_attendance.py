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
# Attendance page (GET) — route removed, now returns 404
# ---------------------------------------------------------------------------


def test_attendance_page_no_longer_exists(admin_client, db):
    """GET /attendance/{id} returns 404 after route deletion."""
    event = _make_event(db)
    resp = admin_client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 404


def test_attendance_missing_event_no_longer_exists(admin_client):
    """GET /attendance/99999 returns 404 after route deletion."""
    resp = admin_client.get("/attendance/99999", follow_redirects=False)
    assert resp.status_code == 404


def test_attendance_login_redirect_no_longer_exists(client, db):
    """GET /attendance/{id} returns 404 (route gone, not a login redirect)."""
    event = _make_event(db, title="Auth Test Event")
    resp = client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 404


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


# ---------------------------------------------------------------------------
# backfill_attendance_for_player
# ---------------------------------------------------------------------------


def _setup_team_season(db):
    """Return (team, season, player, mem) with PlayerTeam row committed."""
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    season = Season(name="Backfill Season", is_active=True)
    team = Team(name="Backfill Team")
    db.add_all([season, team])
    db.flush()
    player = Player(first_name="Back", last_name="Fill", is_active=True)
    db.add(player)
    db.flush()
    mem = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, priority=1)
    db.add(mem)
    db.commit()
    return team, season, player


def test_backfill_past_events_set_absent(db):
    """Past events (event_date < today) are always set to 'absent'."""
    from datetime import date, timedelta

    from services.attendance_service import backfill_attendance_for_player

    team, season, player = _setup_team_season(db)
    past_event = Event(
        title="Past Training",
        event_type="training",
        event_date=date.today() - timedelta(days=7),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(past_event)
    db.commit()

    count = backfill_attendance_for_player(db, player.id, team.id, season.id)

    assert count == 1
    att = db.query(Attendance).filter(Attendance.event_id == past_event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.status == "absent"


def test_backfill_future_events_use_default_status(db):
    """Future events use _default_status (presence_type='all' → present, else → unknown)."""
    from datetime import date, timedelta

    from services.attendance_service import backfill_attendance_for_player

    team, season, player = _setup_team_season(db)
    future_unknown = Event(
        title="Future Training",
        event_type="training",
        event_date=date.today() + timedelta(days=7),
        team_id=team.id,
        season_id=season.id,
        presence_type="normal",
    )
    future_present = Event(
        title="Future All",
        event_type="training",
        event_date=date.today() + timedelta(days=14),
        team_id=team.id,
        season_id=season.id,
        presence_type="all",
    )
    db.add_all([future_unknown, future_present])
    db.commit()

    count = backfill_attendance_for_player(db, player.id, team.id, season.id)

    assert count == 2
    att_u = (
        db.query(Attendance).filter(Attendance.event_id == future_unknown.id, Attendance.player_id == player.id).first()
    )
    att_p = (
        db.query(Attendance).filter(Attendance.event_id == future_present.id, Attendance.player_id == player.id).first()
    )
    assert att_u.status == "unknown"
    assert att_p.status == "present"


def test_backfill_does_not_overwrite_existing(db):
    """Existing Attendance rows are never overwritten."""
    from datetime import date, timedelta

    from services.attendance_service import backfill_attendance_for_player

    team, season, player = _setup_team_season(db)
    event = Event(
        title="Existing Att Event",
        event_type="training",
        event_date=date.today() + timedelta(days=3),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()
    existing = Attendance(event_id=event.id, player_id=player.id, status="maybe")
    db.add(existing)
    db.commit()

    count = backfill_attendance_for_player(db, player.id, team.id, season.id)

    assert count == 0
    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att.status == "maybe"


def test_backfill_skips_inactive_player(db):
    """Inactive players get no attendance records created."""
    from datetime import date, timedelta

    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team
    from services.attendance_service import backfill_attendance_for_player

    season = Season(name="Inactive Season", is_active=False)
    team = Team(name="Inactive Team")
    db.add_all([season, team])
    db.flush()
    inactive = Player(first_name="In", last_name="Active", is_active=False)
    db.add(inactive)
    db.flush()
    db.add(PlayerTeam(player_id=inactive.id, team_id=team.id, season_id=season.id, priority=1))
    event = Event(
        title="Skip Inactive",
        event_type="training",
        event_date=date.today() + timedelta(days=1),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    count = backfill_attendance_for_player(db, inactive.id, team.id, season.id)

    assert count == 0
    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == inactive.id).first()
    assert att is None


# ---------------------------------------------------------------------------
# Player borrowing
# ---------------------------------------------------------------------------


def _make_team_season(db):
    """Return (team, season) committed to db."""
    from models.season import Season
    from models.team import Team

    season = Season(name="Borrow Season", is_active=True)
    team = Team(name="Borrow Team")
    db.add_all([season, team])
    db.commit()
    return team, season


def test_borrow_creates_attendance_with_team(admin_client, db):
    """Borrowing an active player creates an Attendance row with borrowed_from_team_id set."""
    from models.player_team import PlayerTeam
    from models.team import Team

    team, season = _make_team_season(db)
    event = Event(
        title="Borrow Event",
        event_type="training",
        event_date=date(2026, 6, 1),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    other_team = Team(name="Other Team")
    db.add(other_team)
    db.flush()
    player = _make_player(db, "Guest", "Player")
    db.add(PlayerTeam(player_id=player.id, team_id=other_team.id, season_id=season.id, priority=1))
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["team_name"] == "Other Team"

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.borrowed_from_team_id == other_team.id
    assert att.status == "unknown"


def test_borrow_duplicate_rejected(admin_client, db):
    """Borrowing a player already attending returns already_attending error."""
    event = _make_event(db, title="Dup Event")
    player = _make_player(db, "Dup", "Player")
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "already_attending"


def test_borrow_inactive_player_rejected(admin_client, db):
    """Borrowing an inactive player returns player_not_found error."""
    event = _make_event(db, title="Inactive Borrow Event")
    inactive = Player(first_name="In", last_name="Active", is_active=False)
    db.add(inactive)
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": inactive.id},
        follow_redirects=False,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "player_not_found"


def test_borrow_no_season_stores_null_team(admin_client, db):
    """Event with season_id=None: borrow succeeds with borrowed_from_team_id=None."""
    event = Event(title="No Season Borrow", event_type="training", event_date=date(2026, 7, 1), season_id=None)
    db.add(event)
    db.commit()
    player = _make_player(db, "NoSeason", "Guest")

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["team_name"] is None

    att = db.query(Attendance).filter(Attendance.event_id == event.id, Attendance.player_id == player.id).first()
    assert att is not None
    assert att.borrowed_from_team_id is None


def test_player_search_excludes_existing_attendees(admin_client, db):
    """GET /players/search?q=&exclude_event_id= excludes players already attending."""
    from models.season import Season
    from models.team import Team

    season = Season(name="Search Season", is_active=True)
    team = Team(name="Search Team")
    db.add_all([season, team])
    db.flush()

    event = Event(
        title="Search Event",
        event_type="training",
        event_date=date(2026, 6, 3),
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    already = _make_player(db, "Already", "There")
    not_yet = _make_player(db, "Notyet", "Player")

    db.add(Attendance(event_id=event.id, player_id=already.id, status="present"))
    db.commit()

    resp = admin_client.get(
        f"/players/search?q=player&exclude_event_id={event.id}",
        follow_redirects=False,
    )
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert already.id not in ids
    assert not_yet.id in ids
