"""tests/test_absence_service.py — Absence service tests."""

import pytest
from datetime import date
from sqlalchemy.orm import Session

from models.player import Player
from models.player_absence import PlayerAbsence
from services.absence_service import is_date_in_absence


def test_is_date_in_absence_period_within_range(db: Session):
    """Period absence should match dates within start_date to end_date (inclusive)."""
    # Create a player
    player = Player(first_name="John", last_name="Doe", is_active=True)
    db.add(player)
    db.commit()

    # Create a period absence: April 10-20
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    # Test dates within range
    assert is_date_in_absence(player.id, date(2026, 4, 10), db) is True  # start
    assert is_date_in_absence(player.id, date(2026, 4, 15), db) is True  # middle
    assert is_date_in_absence(player.id, date(2026, 4, 20), db) is True  # end

    # Test dates outside range
    assert is_date_in_absence(player.id, date(2026, 4, 9), db) is False
    assert is_date_in_absence(player.id, date(2026, 4, 21), db) is False


def test_is_date_in_absence_period_no_match(db: Session):
    """Period absence should not match dates outside the range."""
    player = Player(first_name="Jane", last_name="Smith", is_active=True)
    db.add(player)
    db.commit()

    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    db.add(absence)
    db.commit()

    assert is_date_in_absence(player.id, date(2026, 5, 1), db) is False


def test_is_date_in_absence_no_absences(db: Session):
    """Player with no absences should return False."""
    player = Player(first_name="Bob", last_name="Jones", is_active=True)
    db.add(player)
    db.commit()

    assert is_date_in_absence(player.id, date(2026, 4, 15), db) is False
