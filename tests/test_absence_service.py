"""tests/test_absence_service.py — Absence service tests."""

import pytest
from datetime import date
from sqlalchemy.orm import Session

from models.player import Player
from models.player_absence import PlayerAbsence
from models.season import Season
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


def test_is_date_in_absence_recurring_weekly(db: Session):
    """Recurring absence with FREQ=WEEKLY;BYDAY=FR should match Fridays."""
    player = Player(first_name="Alice", last_name="Wonder", is_active=True)
    db.add(player)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Every Friday until end of season
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="recurring",
        rrule="FREQ=WEEKLY;BYDAY=FR",
        rrule_until=date(2026, 6, 30),
        season_id=season.id,
        reason="Weekly training conflict",
    )
    db.add(absence)
    db.commit()

    # April 11, 18, 25 are Fridays
    assert is_date_in_absence(player.id, date(2026, 4, 11), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 18), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 25), db) is True

    # April 12 is Saturday
    assert is_date_in_absence(player.id, date(2026, 4, 12), db) is False


def test_is_date_in_absence_recurring_expired(db: Session):
    """Recurring absence should not match dates after rrule_until."""
    player = Player(first_name="Charlie", last_name="Brown", is_active=True)
    db.add(player)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Every Friday until April 30
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="recurring",
        rrule="FREQ=WEEKLY;BYDAY=FR",
        rrule_until=date(2026, 4, 30),
        season_id=season.id,
    )
    db.add(absence)
    db.commit()

    # May 1 is a Friday, but after rrule_until
    assert is_date_in_absence(player.id, date(2026, 5, 1), db) is False
    # But April 25 (Friday) should match
    assert is_date_in_absence(player.id, date(2026, 4, 25), db) is True
