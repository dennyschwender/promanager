"""tests/test_absence_routes.py — Absence API route tests."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user_team import UserTeam


def test_player_get_own_absences(member_client: TestClient, member_user, db):
    """Player should be able to view their own absences."""
    # Create a player linked to the member user
    player = Player(first_name="Member", last_name="Player", is_active=True, user_id=member_user.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Create an absence for the player
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    # Get absences
    response = member_client.get(f"/api/players/{player.id}/absences")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["absence_type"] == "period"
    assert data[0]["reason"] == "Vacation"


def test_player_cannot_view_other_absences(member_client: TestClient, db):
    """Player should NOT be able to view another player's absences."""
    other_player = Player(first_name="Other", last_name="Player", is_active=True)
    db.add(other_player)
    db.commit()
    db.refresh(other_player)

    absence = PlayerAbsence(
        player_id=other_player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    db.add(absence)
    db.commit()

    response = member_client.get(f"/api/players/{other_player.id}/absences")

    assert response.status_code == 403


def test_create_period_absence(member_client: TestClient, member_user, db):
    """Player should be able to create a period absence for themselves."""
    # Create a player linked to the member user
    player = Player(first_name="Member", last_name="Player", is_active=True, user_id=member_user.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    response = member_client.post(
        f"/api/players/{player.id}/absences",
        json={
            "absence_type": "period",
            "start_date": "2026-04-10",
            "end_date": "2026-04-20",
            "reason": "Vacation",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["absence_type"] == "period"
    assert data["reason"] == "Vacation"

    # Verify in DB
    absence = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player.id).first()
    assert absence is not None
    assert absence.start_date == date(2026, 4, 10)
    assert absence.end_date == date(2026, 4, 20)


def test_create_recurring_absence(member_client: TestClient, member_user, db):
    """Player should be able to create a recurring absence."""
    # Create a player linked to the member user
    player = Player(first_name="Member", last_name="Player", is_active=True, user_id=member_user.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()
    db.refresh(season)

    response = member_client.post(
        f"/api/players/{player.id}/absences",
        json={
            "absence_type": "recurring",
            "rrule": "FREQ=WEEKLY;BYDAY=FR",
            "season_id": season.id,
            "reason": "Friday training",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["absence_type"] == "recurring"
    assert data["rrule"] == "FREQ=WEEKLY;BYDAY=FR"
    assert data["season_id"] == season.id

    # Verify in DB
    absence = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player.id).first()
    assert absence is not None
    assert absence.rrule == "FREQ=WEEKLY;BYDAY=FR"


def test_cannot_create_absence_in_past(member_client: TestClient, member_user, db):
    """Should not allow creating absences in the past."""
    player = Player(first_name="Member", last_name="Player", is_active=True, user_id=member_user.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    response = member_client.post(
        f"/api/players/{player.id}/absences",
        json={
            "absence_type": "period",
            "start_date": "2026-04-01",
            "end_date": "2026-04-05",
            "reason": "Vacation",
        },
    )

    assert response.status_code == 400


def test_admin_can_create_absence_for_any_player(admin_client, db):
    """Admin should be able to create absences for any player."""
    player = Player(first_name="Any", last_name="Player", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    response = admin_client.post(
        f"/api/players/{player.id}/absences",
        json={
            "absence_type": "period",
            "start_date": "2026-04-10",
            "end_date": "2026-04-20",
            "reason": "Vacation",
        },
    )

    assert response.status_code == 200


def test_coach_can_create_absence_for_team_player(client, db):
    """Coach should be able to create absences for their team's players."""
    from services.auth_service import create_user, create_session_cookie

    # Create a coach user
    coach_user = create_user(db, "coach", "coach@test.com", "coachpass", role="coach")

    # Create a team and season
    team = Team(name="Team A")
    db.add(team)
    db.commit()
    db.refresh(team)

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()
    db.refresh(season)

    # Link coach to team
    user_team = UserTeam(user_id=coach_user.id, team_id=team.id, season_id=season.id)
    db.add(user_team)
    db.commit()

    # Create a player and link to team
    player = Player(first_name="Team", last_name="Player", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    player_team = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(player_team)
    db.commit()

    # Create a coach client
    coach_client = client
    coach_client.cookies.set("session_user_id", create_session_cookie(coach_user.id))

    response = coach_client.post(
        f"/api/players/{player.id}/absences",
        json={
            "absence_type": "period",
            "start_date": "2026-04-10",
            "end_date": "2026-04-20",
            "reason": "Vacation",
        },
    )

    assert response.status_code == 200


def test_delete_absence(member_client: TestClient, member_user, db):
    """Player should be able to delete their own absence."""
    player = Player(first_name="Member", last_name="Player", is_active=True, user_id=member_user.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)

    response = member_client.delete(f"/api/players/{player.id}/absences/{absence.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify deleted
    deleted_absence = db.query(PlayerAbsence).filter(PlayerAbsence.id == absence.id).first()
    assert deleted_absence is None


def test_cannot_delete_other_player_absence(member_client: TestClient, member_user, db):
    """Player should not be able to delete another player's absence."""
    other_player = Player(first_name="Other", last_name="Player", is_active=True)
    db.add(other_player)
    db.commit()
    db.refresh(other_player)

    absence = PlayerAbsence(
        player_id=other_player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)

    response = member_client.delete(f"/api/players/{other_player.id}/absences/{absence.id}")

    assert response.status_code == 403


def test_unauthenticated_cannot_access_absences(client: TestClient, db):
    """Unauthenticated users should be redirected."""
    player = Player(first_name="Any", last_name="Player", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    response = client.get(f"/api/players/{player.id}/absences", follow_redirects=False)

    assert response.status_code == 302  # Redirect to login
