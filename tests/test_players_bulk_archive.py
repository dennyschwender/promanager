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
    p = Player(first_name="Hidden", last_name="Archived", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    resp = admin_client.get("/players")
    assert resp.status_code == 200
    assert "Hidden" not in resp.text


def test_archived_filter_only(admin_client, db):
    """?archived=only shows only archived players."""
    active = Player(first_name="Visible", last_name="ActivePlayer", is_active=True)
    archived = Player(first_name="Gone", last_name="Player", is_active=True,
                      archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=only")
    assert resp.status_code == 200
    assert "Gone" in resp.text
    assert "Visible" not in resp.text


def test_archived_filter_all(admin_client, db):
    """?archived=all shows both active and archived players."""
    active = Player(first_name="Active", last_name="P", is_active=True)
    archived = Player(first_name="Gone", last_name="P", is_active=True,
                      archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=all")
    assert resp.status_code == 200
    assert "Active" in resp.text
    assert "Gone" in resp.text
