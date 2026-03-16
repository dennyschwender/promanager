"""Tests for /seasons routes."""

from models.season import Season

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_seasons_list(admin_client):
    resp = admin_client.get("/seasons", follow_redirects=False)
    assert resp.status_code == 200


def test_seasons_requires_login(client):
    resp = client.get("/seasons", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_season(admin_client, db):
    resp = admin_client.post(
        "/seasons/new",
        data={"name": "2025/26", "start_date": "2025-09-01", "end_date": "2026-05-31"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.query(Season).filter(Season.name == "2025/26").first() is not None


def test_create_season_blank_name(admin_client):
    resp = admin_client.post(
        "/seasons/new",
        data={"name": "   ", "start_date": "", "end_date": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_season(admin_client, db):
    season = Season(name="OldName")
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = admin_client.post(
        f"/seasons/{season.id}/edit",
        data={"name": "NewName", "start_date": "", "end_date": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(season)
    assert season.name == "NewName"


# ---------------------------------------------------------------------------
# Activate
# ---------------------------------------------------------------------------


def test_activate_season(admin_client, db):
    s1 = Season(name="Season A", is_active=True)
    s2 = Season(name="Season B", is_active=False)
    db.add_all([s1, s2])
    db.commit()
    db.refresh(s1)
    db.refresh(s2)

    resp = admin_client.post(f"/seasons/{s2.id}/activate", follow_redirects=False)
    assert resp.status_code == 302

    db.refresh(s1)
    db.refresh(s2)
    assert s2.is_active is True
    assert s1.is_active is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_season(admin_client, db):
    season = Season(name="ToDelete")
    db.add(season)
    db.commit()
    db.refresh(season)
    sid = season.id

    resp = admin_client.post(f"/seasons/{sid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Season, sid) is None


def test_copy_roster(admin_client, db):
    """Copy-roster duplicates PlayerTeam rows from source to target season."""
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.team import Team

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Copy", last_name="Test", is_active=True)
    db.add(player)
    db.flush()

    db.add(
        PlayerTeam(
            player_id=player.id,
            team_id=team.id,
            season_id=s1.id,
            priority=1,
            role="player",
            injured_until=None,
            absent_by_default=False,
        )
    )
    db.commit()

    resp = admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    copied = (
        db.query(PlayerTeam)
        .filter(
            PlayerTeam.player_id == player.id,
            PlayerTeam.season_id == s2.id,
        )
        .first()
    )
    assert copied is not None
    assert copied.priority == 1
    assert copied.role == "player"


def test_copy_roster_resets_injury_fields(admin_client, db):
    """Copy-roster resets injured_until and absent_by_default on copied rows."""
    from datetime import date

    from models.player import Player
    from models.player_team import PlayerTeam
    from models.team import Team

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Injured", last_name="Player", is_active=True)
    db.add(player)
    db.flush()

    db.add(
        PlayerTeam(
            player_id=player.id,
            team_id=team.id,
            season_id=s1.id,
            priority=1,
            injured_until=date(2025, 3, 1),
            absent_by_default=True,
        )
    )
    db.commit()

    admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )

    copied = db.query(PlayerTeam).filter(PlayerTeam.season_id == s2.id).first()
    assert copied.injured_until is None
    assert copied.absent_by_default is False


def test_copy_roster_skips_duplicates(admin_client, db):
    """Copy-roster is idempotent — running twice doesn't duplicate rows."""
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.team import Team

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Dupe", last_name="Test", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s1.id, priority=1))
    db.commit()

    resp1 = admin_client.post(
        f"/seasons/{s2.id}/copy-roster", data={"source_season_id": str(s1.id)}, follow_redirects=False
    )
    resp2 = admin_client.post(
        f"/seasons/{s2.id}/copy-roster", data={"source_season_id": str(s1.id)}, follow_redirects=False
    )
    assert resp1.status_code == 302
    assert resp2.status_code == 302

    count = db.query(PlayerTeam).filter(PlayerTeam.season_id == s2.id).count()
    assert count == 1


def test_copy_roster_self_copy_returns_400(admin_client, db):
    """copy-roster with source == target returns 400."""
    season = Season(name="2025/26", is_active=True)
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = admin_client.post(
        f"/seasons/{season.id}/copy-roster",
        data={"source_season_id": str(season.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_copy_roster_empty_source_returns_zero(admin_client, db):
    """Copy-roster with an empty source season returns 302 and copies 0 rows."""
    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    db.add_all([s1, s2])
    db.commit()

    resp = admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_copy_roster_requires_admin(member_client, db):
    """copy-roster returns 403 for non-admin users."""
    season = Season(name="2025/26", is_active=True)
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = member_client.post(
        f"/seasons/{season.id}/copy-roster",
        data={"source_season_id": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
