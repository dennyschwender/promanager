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
    p = Player(first_name="Solo", last_name="Unarchive", is_active=True,
               archived_at=datetime.now(timezone.utc))
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
    p = Player(first_name="Protected", last_name="Player", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = member_client.post(f"/players/{p.id}/unarchive", follow_redirects=False)
    assert resp.status_code == 403
