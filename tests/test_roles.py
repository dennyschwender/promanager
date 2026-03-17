import pytest
from models.user_team import UserTeam


def test_user_team_importable():
    assert UserTeam.__tablename__ == "user_team"


from datetime import date
from sqlalchemy.orm import Session
from models.user import User
from routes._auth_helpers import get_coach_teams, check_team_access, NotAuthorized


def _make_coach(db: Session) -> User:
    from services.auth_service import hash_password
    u = User(username="coach1", email="coach1@test.com",
             hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(u)
    db.flush()
    return u


def test_get_coach_teams_returns_empty_for_unassigned(db):
    coach = _make_coach(db)
    result = get_coach_teams(coach, db)
    assert result == set()


def test_get_coach_teams_returns_assigned_team(db):
    from models.team import Team
    coach = _make_coach(db)
    team = Team(name="Test Team")
    db.add(team)
    db.flush()
    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.flush()
    result = get_coach_teams(coach, db)
    assert team.id in result


def test_check_team_access_admin_always_passes(db, admin_user):
    # Should not raise for any team_id
    check_team_access(admin_user, 99999, db)


def test_check_team_access_coach_denied_unassigned(db):
    coach = _make_coach(db)
    with pytest.raises(NotAuthorized):
        check_team_access(coach, 99999, db)


def test_check_team_access_coach_passes_assigned(db):
    from models.team import Team
    coach = _make_coach(db)
    team = Team(name="Allowed Team")
    db.add(team)
    db.flush()
    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.flush()
    check_team_access(coach, team.id, db)  # should not raise


def test_public_schedule_no_auth(client):
    """Public /schedule returns 200 without authentication."""
    resp = client.get("/schedule")
    assert resp.status_code == 200


def test_admin_can_assign_coach(admin_client, db):
    from models.team import Team
    from models.user import User
    from services.auth_service import hash_password

    team = Team(name="Team Alpha")
    db.add(team)
    coach_user = User(username="coachy", email="coachy@test.com",
                      hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach_user)
    db.commit()

    resp = admin_client.post(
        f"/teams/{team.id}/coaches",
        data={"user_id": coach_user.id, "season_id": "", "csrf_token": "test"},
    )
    assert resp.status_code in (200, 302)
    from models.user_team import UserTeam
    ut = db.query(UserTeam).filter_by(user_id=coach_user.id, team_id=team.id).first()
    assert ut is not None


def test_admin_can_remove_coach(admin_client, db):
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password

    team = Team(name="Team Beta")
    db.add(team)
    coach_user = User(username="coachy2", email="coachy2@test.com",
                      hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach_user)
    db.flush()
    ut = UserTeam(user_id=coach_user.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.commit()

    resp = admin_client.post(f"/teams/{team.id}/coaches/{ut.id}/delete",
                             data={"csrf_token": "test"})
    assert resp.status_code in (200, 302)
    assert db.get(UserTeam, ut.id) is None


def test_public_schedule_has_no_player_names(client, db):
    """Schedule page does not expose player names."""
    from models.player import Player
    p = Player(first_name="Secret", last_name="Player", is_active=True)
    db.add(p)
    db.commit()
    resp = client.get("/schedule")
    assert "Secret" not in resp.text
    assert "Player" not in resp.text


def _setup_coach_with_team(db):
    """Helper: creates a coach user, a team, a season, and UserTeam assignment. Returns (coach, team, season)."""
    from datetime import date
    from models.season import Season
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password

    season = Season(name="S2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    team = Team(name="Coach Team")
    db.add_all([season, team])
    db.flush()

    coach = User(username="coach_ev", email="coach_ev@test.com",
                 hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach)
    db.flush()

    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.commit()
    return coach, team, season


def _coach_client(app, db_override, coach_user):
    """Build a TestClient logged in as the given coach user."""
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.csrf import require_csrf, require_csrf_header
    from services.auth_service import create_session_cookie

    async def _no_csrf():
        pass

    app.dependency_overrides[get_db] = lambda: (yield db_override)
    app.dependency_overrides[require_csrf] = _no_csrf
    app.dependency_overrides[require_csrf_header] = _no_csrf

    cookie_val = create_session_cookie(coach_user.id)
    c = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    c.cookies.set("session_user_id", cookie_val)
    return c


def test_coach_can_create_event_on_assigned_team(db):
    from datetime import date
    from app.main import app

    coach, team, season = _setup_coach_with_team(db)
    c = _coach_client(app, db, coach)
    resp = c.post("/events/new", data={
        "title": "Training 1",
        "event_type": "training",
        "event_date": "2025-06-01",
        "team_id": str(team.id),
        "season_id": str(season.id),
        "csrf_token": "test",
    })
    app.dependency_overrides.clear()
    assert resp.status_code == 302


def test_coach_cannot_create_event_on_unassigned_team(db):
    from datetime import date
    from models.team import Team
    from app.main import app

    coach, _, season = _setup_coach_with_team(db)
    other_team = Team(name="Other Team")
    db.add(other_team)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.post("/events/new", data={
        "title": "Should Fail",
        "event_type": "training",
        "event_date": "2025-06-01",
        "team_id": str(other_team.id),
        "season_id": str(season.id),
        "csrf_token": "test",
    })
    app.dependency_overrides.clear()
    assert resp.status_code == 403
