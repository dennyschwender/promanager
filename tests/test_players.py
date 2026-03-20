"""Tests for /players routes."""

from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
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

    resp = admin_client.post(f"/players/{pid}/archive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(player)
    assert player.archived_at is not None   # soft-archived, not gone


# ---------------------------------------------------------------------------
# Filter by team
# ---------------------------------------------------------------------------


def test_players_filter_by_team(admin_client, db):
    from models.season import Season

    season = Season(name="2025/26", is_active=True)
    team = Team(name="FilterTeam")
    db.add_all([season, team])
    db.commit()
    db.refresh(season)
    db.refresh(team)

    p1 = Player(first_name="Eve", last_name="InTeam", is_active=True)
    p2 = Player(first_name="Frank", last_name="NoTeam", is_active=True)
    db.add_all([p1, p2])
    db.flush()
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, priority=1))
    db.commit()

    resp = admin_client.get(f"/players?team_id={team.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Eve" in resp.content
    assert b"Frank" not in resp.content


def test_players_list_filters_by_active_season(admin_client, db):
    """Player list defaults to active season — only shows players in that season."""
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    p1 = Player(first_name="InActive", last_name="Season", is_active=True)
    p2 = Player(first_name="InCurrent", last_name="Season", is_active=True)
    db.add_all([p1, p2])
    db.flush()

    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    resp = admin_client.get(f"/players?season_id={s2.id}&team_id={team.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"InCurrent" in resp.content
    assert b"InActive" not in resp.content


def test_sync_memberships_only_touches_target_season(db):
    """Editing a player in season A must not delete their season B membership."""
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team
    from routes.players import _sync_memberships

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Multi", last_name="Season", is_active=True)
    db.add(player)
    db.flush()

    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    _sync_memberships(db, player, [], season_id=s2.id)
    db.commit()

    remaining = db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id).all()
    assert len(remaining) == 1
    assert remaining[0].season_id == s1.id


def test_player_team_has_season_id(db):
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    season = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    player = Player(first_name="Anna", last_name="Test", is_active=True)
    db.add_all([season, team, player])
    db.flush()

    pt = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, priority=1)
    db.add(pt)
    db.commit()
    db.refresh(pt)

    assert pt.season_id == season.id
    assert pt.season is not None
    assert pt.season.name == "2025/26"


# ---------------------------------------------------------------------------
# Helpers (used by bulk-assign and bulk-update tests)
# ---------------------------------------------------------------------------

def _make_season(db, name="2025/26", is_active=True):
    s = Season(name=name, is_active=is_active)
    db.add(s)
    db.flush()
    return s


def _make_team(db, name="U21"):
    t = Team(name=name)
    db.add(t)
    db.flush()
    return t


def _make_player(db, first="Alice", last="Smith"):
    p = Player(first_name=first, last_name=last, is_active=True)
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------------------
# Bulk assign
# ---------------------------------------------------------------------------

def test_bulk_assign_creates_player_teams(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Alice", "A")
    p2 = _make_player(db, "Bob", "B")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-assign",
        json={"player_ids": [p1.id, p2.id], "team_id": team.id, "season_id": season.id},
        headers={"X-CSRF-Token": "test"},  # overridden in fixture
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []
    rows = db.query(PlayerTeam).filter(PlayerTeam.team_id == team.id).all()
    assert len(rows) == 2


def test_bulk_assign_skips_existing(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Alice", "A")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-assign",
        json={"player_ids": [p1.id], "team_id": team.id, "season_id": season.id},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned"] == 0
    assert data["skipped"] == 1


def test_bulk_assign_requires_admin(client, db):
    resp = client.post(
        "/players/bulk-assign",
        json={"player_ids": [1], "team_id": 1, "season_id": 1},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------

def test_bulk_update_player_fields(admin_client, db):
    p = _make_player(db, "Alice", "Old")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={"players": [{"id": p.id, "email": "alice@new.com", "is_active": False}]},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]
    assert data["errors"] == []
    db.refresh(p)
    assert p.email == "alice@new.com"
    assert p.is_active is False


def test_bulk_update_player_team_fields(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Bob", "B")
    db.add(PlayerTeam(player_id=p.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "shirt_number": 7}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]
    pt = db.get(PlayerTeam, (p.id, team.id, season.id))
    assert pt.shirt_number == 7


def test_bulk_update_creates_player_team_if_missing(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Carol", "C")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "position": "goalie"}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    pt = db.get(PlayerTeam, (p.id, team.id, season.id))
    assert pt is not None
    assert pt.position == "goalie"


def test_bulk_update_shirt_number_conflict(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Dan", "D")
    p2 = _make_player(db, "Eve", "E")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, shirt_number=9))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p2.id, "shirt_number": 9}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p2.id in [e["id"] for e in data["errors"]]
    assert data["saved"] == []


def test_bulk_update_shirt_number_self_conflict_ok(admin_client, db):
    """Submitting the unchanged shirt number for its owner must not conflict."""
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Fred", "F")
    db.add(PlayerTeam(player_id=p.id, team_id=team.id, season_id=season.id, shirt_number=5))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "shirt_number": 5, "position": "goalie"}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]


def test_bulk_update_playerteam_fields_without_team_returns_400(admin_client, db):
    season = _make_season(db)
    p = _make_player(db, "Gail", "G")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            # team_id intentionally omitted
            "players": [{"id": p.id, "shirt_number": 3}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 400


def test_bulk_update_partial_success(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Han", "H")
    p2 = _make_player(db, "Ida", "I")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, shirt_number=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [
                {"id": p1.id, "email": "han@ok.com"},   # succeeds
                {"id": p2.id, "shirt_number": 1},       # conflicts with p1
            ],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p1.id in data["saved"]
    assert p2.id in [e["id"] for e in data["errors"]]
