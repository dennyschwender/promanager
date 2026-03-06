"""Tests for /teams routes."""
import pytest
from models.team import Team


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_teams_list(admin_client):
    resp = admin_client.get("/teams", follow_redirects=False)
    assert resp.status_code == 200


def test_teams_requires_login(client):
    resp = client.get("/teams", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_team(admin_client, db):
    resp = admin_client.post(
        "/teams/new",
        data={"name": "Falcons", "description": "The best team", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.query(Team).filter(Team.name == "Falcons").first() is not None


def test_create_team_blank_name(admin_client):
    resp = admin_client.post(
        "/teams/new",
        data={"name": "", "description": "", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_team(admin_client, db):
    team = Team(name="OldTeam")
    db.add(team)
    db.commit()
    db.refresh(team)

    resp = admin_client.post(
        f"/teams/{team.id}/edit",
        data={"name": "NewTeam", "description": "", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(team)
    assert team.name == "NewTeam"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_team(admin_client, db):
    team = Team(name="ToDelete")
    db.add(team)
    db.commit()
    db.refresh(team)
    tid = team.id

    resp = admin_client.post(f"/teams/{tid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Team, tid) is None
