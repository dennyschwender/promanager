"""Tests for /players routes."""
import pytest
from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_players_list(admin_client):
    resp = admin_client.get("/players", follow_redirects=False)
    assert resp.status_code == 200


def test_players_requires_login(client):
    resp = client.get("/players", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_player(admin_client, db):
    resp = admin_client.post(
        "/players/new",
        data={
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@test.com",
            "phone": "",
            "team_id": "",
            "user_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    player = db.query(Player).filter(Player.first_name == "Alice").first()
    assert player is not None
    assert player.last_name == "Smith"


def test_create_player_missing_name(admin_client):
    resp = admin_client.post(
        "/players/new",
        data={
            "first_name": "",
            "last_name": "",
            "email": "",
            "phone": "",
            "team_id": "",
            "user_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_player_detail(admin_client, db):
    player = Player(first_name="Bob", last_name="Jones", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    resp = admin_client.get(f"/players/{player.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Bob" in resp.content


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_player(admin_client, db):
    player = Player(first_name="Carol", last_name="Old", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    resp = admin_client.post(
        f"/players/{player.id}/edit",
        data={
            "first_name": "Carol",
            "last_name": "New",
            "email": "",
            "phone": "",
            "team_id": "",
            "user_id": "",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(player)
    assert player.last_name == "New"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_player(admin_client, db):
    player = Player(first_name="Dave", last_name="Delete", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)
    pid = player.id

    resp = admin_client.post(f"/players/{pid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Player, pid) is None


# ---------------------------------------------------------------------------
# Filter by team
# ---------------------------------------------------------------------------


def test_players_filter_by_team(admin_client, db):
    team = Team(name="FilterTeam")
    db.add(team)
    db.commit()
    db.refresh(team)

    p1 = Player(first_name="Eve", last_name="InTeam", is_active=True)
    p2 = Player(first_name="Frank", last_name="NoTeam", is_active=True)
    db.add_all([p1, p2])
    db.flush()
    # Assign p1 to the team via the association table
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, priority=1))
    db.commit()

    resp = admin_client.get(f"/players?team_id={team.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Eve" in resp.content
    assert b"Frank" not in resp.content
