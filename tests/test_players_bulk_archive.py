"""Tests for player archive functionality."""

from __future__ import annotations

from datetime import datetime, timezone

from models.player import Player


def test_player_has_archived_at_field(db):
    """Player model has an archived_at column defaulting to None."""
    p = Player(first_name="Arch", last_name="Test", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.archived_at is None


def test_archived_filter_hides_archived_by_default(admin_client, db):
    """Default /players view excludes archived players."""
    p = Player(first_name="Hidden", last_name="Archived", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    resp = admin_client.get("/players")
    assert resp.status_code == 200
    assert "Hidden" not in resp.text


def test_archived_filter_only(admin_client, db):
    """?archived=only shows only archived players."""
    active = Player(first_name="Visible", last_name="ActivePlayer", is_active=True)
    archived = Player(first_name="Gone", last_name="Player", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=only")
    assert resp.status_code == 200
    assert "Gone" in resp.text
    assert "Visible" not in resp.text


def test_archived_filter_all(admin_client, db):
    """?archived=all shows both active and archived players."""
    active = Player(first_name="Active", last_name="P", is_active=True)
    archived = Player(first_name="Gone", last_name="P", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=all")
    assert resp.status_code == 200
    assert "Active" in resp.text
    assert "Gone" in resp.text


def test_single_player_archive(admin_client, db):
    """POST /players/{id}/archive sets archived_at."""
    p = Player(first_name="Solo", last_name="Archive", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post(f"/players/{p.id}/archive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(p)
    assert p.archived_at is not None


def test_single_player_unarchive(admin_client, db):
    """POST /players/{id}/unarchive clears archived_at."""
    p = Player(first_name="Solo", last_name="Unarchive", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post(f"/players/{p.id}/unarchive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(p)
    assert p.archived_at is None


def test_member_cannot_archive(member_client, db):
    """Non-admin gets 403 when trying to archive a player."""
    p = Player(first_name="Protected", last_name="Player", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = member_client.post(f"/players/{p.id}/archive", follow_redirects=False)
    assert resp.status_code == 403


def test_member_cannot_unarchive(member_client, db):
    """Non-admin gets 403 when trying to unarchive a player."""
    p = Player(first_name="Protected", last_name="Player", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = member_client.post(f"/players/{p.id}/unarchive", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_archive_sets_archived_at(admin_client, db):
    """bulk-archive sets archived_at on multiple players."""
    p1 = Player(first_name="Bulk1", last_name="A", is_active=True)
    p2 = Player(first_name="Bulk2", last_name="A", is_active=True)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    resp = admin_client.post(
        "/players/bulk-archive",
        json={"player_ids": [p1.id, p2.id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 2
    assert data["skipped"] == 0
    db.refresh(p1)
    db.refresh(p2)
    assert p1.archived_at is not None
    assert p2.archived_at is not None


def test_bulk_archive_skips_already_archived(admin_client, db):
    """bulk-archive skips players already archived."""
    p = Player(first_name="Already", last_name="Archived", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-archive", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert data["skipped"] == 1


def test_bulk_unarchive_clears_archived_at(admin_client, db):
    """bulk-unarchive clears archived_at."""
    p = Player(first_name="Restore", last_name="Me", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-unarchive", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["unarchived"] == 1
    db.refresh(p)
    assert p.archived_at is None


def test_bulk_activate(admin_client, db):
    """bulk-activate sets is_active=True."""
    p = Player(first_name="Inactive", last_name="P", is_active=False)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-activate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["activated"] == 1
    db.refresh(p)
    assert p.is_active is True


def test_bulk_deactivate(admin_client, db):
    """bulk-deactivate sets is_active=False."""
    p = Player(first_name="Active", last_name="P", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-deactivate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["deactivated"] == 1
    db.refresh(p)
    assert p.is_active is False


def test_bulk_activate_skips_archived_players(admin_client, db):
    """bulk-activate skips archived players."""
    p = Player(first_name="Arch", last_name="Skip", is_active=False, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-activate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1
    assert resp.json()["activated"] == 0


def test_bulk_deactivate_skips_archived_players(admin_client, db):
    """bulk-deactivate skips archived players."""
    p = Player(first_name="Arch", last_name="Skip2", is_active=True, archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-deactivate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1
    assert resp.json()["deactivated"] == 0


def test_member_cannot_bulk_archive(member_client, db):
    """Non-admin gets 403 on bulk-archive."""
    resp = member_client.post("/players/bulk-archive", json={"player_ids": []})
    assert resp.status_code == 403


def test_bulk_archive_empty_list(admin_client, db):
    """bulk-archive with empty player_ids returns zero counts."""
    resp = admin_client.post("/players/bulk-archive", json={"player_ids": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert data["skipped"] == 0
    assert data["errors"] == []


def test_bulk_archive_not_found_player(admin_client, db):
    """bulk-archive with nonexistent player_id adds to errors."""
    resp = admin_client.post("/players/bulk-archive", json={"player_ids": [99999]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["id"] == 99999
