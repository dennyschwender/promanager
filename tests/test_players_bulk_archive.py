"""Tests for player archive functionality."""
from __future__ import annotations

from models.player import Player


def test_player_has_archived_at_field(db):
    """Player model has an archived_at column defaulting to None."""
    p = Player(first_name="Arch", last_name="Test", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.archived_at is None
