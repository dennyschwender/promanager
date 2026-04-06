"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session

from models.player_absence import PlayerAbsence


def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player.

    Returns True if the date falls within a period absence or a recurring
    absence pattern. Returns False otherwise.
    """
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            # To be implemented in next task
            pass

    return False
