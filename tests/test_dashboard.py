"""Tests for /dashboard route."""

from datetime import date, timedelta

from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from services.auth_service import create_session_cookie, create_user

# ---------------------------------------------------------------------------
# Player Dashboard Tests
# ---------------------------------------------------------------------------


def test_player_dashboard_renders(member_client):
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_player_dashboard_unlinked_member(client, db):
    user = create_user(db, "unlinked", "u@test.com", "pass", role="member", must_change_password=False)
    cookie_val = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie_val)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b"not linked to any player" in resp.content


def test_player_dashboard_no_active_season(member_client, db):
    # Deactivate all seasons
    for s in db.query(Season).all():
        s.is_active = False
    db.flush()
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_player_dashboard_shows_next_event(member_client, db, member_user):
    # Create a team, season, player linked to member_user, and an upcoming event
    season = Season(
        name="Test Season",
        start_date=date.today() - timedelta(days=30),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
    )
    db.add(season)
    db.flush()
    team = Team(name="Test Team")
    db.add(team)
    db.flush()
    player = Player(first_name="Test", last_name="Player", team_id=team.id, user_id=member_user.id)
    db.add(player)
    db.flush()
    pt = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pt)
    event = Event(
        title="Upcoming Match",
        event_type="match",
        event_date=date.today() + timedelta(days=1),
        season_id=season.id,
        team_id=team.id,
    )
    db.add(event)
    db.commit()
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_player_dashboard_computes_attendance_rate(member_client, db, member_user):
    season = Season(
        name="Test Season",
        start_date=date.today() - timedelta(days=60),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
    )
    db.add(season)
    db.flush()
    team = Team(name="Test Team")
    db.add(team)
    db.flush()
    player = Player(first_name="Test", last_name="Player", team_id=team.id, user_id=member_user.id)
    db.add(player)
    db.flush()
    pt = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pt)
    event = Event(
        title="Past Event",
        event_type="training",
        event_date=date.today() - timedelta(days=5),
        season_id=season.id,
        team_id=team.id,
    )
    db.add(event)
    db.flush()
    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Coach Dashboard Tests
# ---------------------------------------------------------------------------


def test_coach_dashboard_renders(admin_client):
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_coach_dashboard_renders_for_coach(client, db):
    user = create_user(db, "coach1", "coach@test.com", "coachpass", role="coach", must_change_password=False)
    cookie_val = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie_val)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_coach_dashboard_shows_stat_cards(admin_client, db):
    # Create a season and a past event with attendance to populate stat cards
    season = Season(
        name="Active Season",
        start_date=date.today() - timedelta(days=60),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
    )
    db.add(season)
    team = Team(name="Test Team")
    db.add(team)
    db.flush()
    player = Player(first_name="Test", last_name="Player", team_id=team.id)
    db.add(player)
    db.flush()
    pt = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pt)
    event = Event(
        title="Past Event",
        event_type="training",
        event_date=date.today() - timedelta(days=5),
        season_id=season.id,
        team_id=team.id,
    )
    db.add(event)
    db.flush()
    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b"team_attendance" in resp.content or b"100%" in resp.content


def test_coach_dashboard_admin_quick_actions(admin_client):
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b"quick_actions" in resp.content or b"Quick Actions" in resp.content


# ---------------------------------------------------------------------------
# Nav Tests
# ---------------------------------------------------------------------------


def test_reports_link_hidden_for_member(member_client):
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b'/reports"' not in resp.content


def test_reports_link_shown_for_admin(admin_client):
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b'/reports"' in resp.content


def test_dashboard_link_active(admin_client):
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b"nav-active" in resp.content


def test_reports_link_hidden_in_footer_for_member(client, db):
    user = create_user(db, "member2", "m2@test.com", "pass", role="member", must_change_password=False)
    cookie_val = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie_val)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b'/reports"' not in resp.content
