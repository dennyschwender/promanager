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


def test_public_schedule_has_no_player_names(client, db):
    """Schedule page does not expose player names."""
    from models.player import Player
    p = Player(first_name="Secret", last_name="Player", is_active=True)
    db.add(p)
    db.commit()
    resp = client.get("/schedule")
    assert "Secret" not in resp.text
    assert "Player" not in resp.text
