"""routes/absences.py — Absence API endpoints."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.season import Season
from models.user_team import UserTeam
from routes._auth_helpers import require_login
from routes._absence_helpers import require_absence_ownership_or_coach
from services.absence_service import apply_absence_to_future_events

router = APIRouter(prefix="/api", tags=["absences"])


def _check_player_access(current_user, player_id: int, db: Session) -> None:
    """Check if user can access/manage this player.

    Raises HTTPException(403) if not authorized.
    """
    # Check if user owns this player or coaches them
    if not current_user.is_admin:
        # Check if player owns it (explicit query avoids lazy-load DetachedInstanceError)
        owns_player = db.query(Player).filter(Player.user_id == current_user.id, Player.id == player_id).first() is not None
        if not owns_player:
            # Check if coach
            if current_user.is_coach:
                user_teams = db.query(UserTeam).filter(UserTeam.user_id == current_user.id).all()
                team_ids = {ut.team_id for ut in user_teams}

                player_teams = db.query(PlayerTeam).filter(
                    PlayerTeam.player_id == player_id,
                    PlayerTeam.team_id.in_(team_ids) if team_ids else False,
                ).all()

                if not player_teams:
                    raise HTTPException(status_code=403, detail="Not authorized")
            else:
                raise HTTPException(status_code=403, detail="Not authorized")


@router.get("/players/{player_id}/absences")
async def get_player_absences(
    player_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get absences for a player (self or if coach of their team)."""
    # Check player exists
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check authorization
    _check_player_access(current_user, player_id, db)

    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()
    return [
        {
            "id": a.id,
            "absence_type": a.absence_type,
            "start_date": a.start_date,
            "end_date": a.end_date,
            "rrule": a.rrule,
            "rrule_until": a.rrule_until,
            "season_id": a.season_id,
            "reason": a.reason,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
        for a in absences
    ]


@router.post("/players/{player_id}/absences")
async def create_player_absence(
    player_id: int,
    body: dict[str, Any] = Body(...),
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a period or recurring absence for a player."""
    # Check player exists
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check authorization
    _check_player_access(current_user, player_id, db)

    absence_type = body.get("absence_type")
    if absence_type not in ["period", "recurring"]:
        raise HTTPException(status_code=400, detail="Invalid absence_type")

    # Validate inputs
    start_date = None
    end_date = None
    rrule = None
    rrule_until = None

    if absence_type == "period":
        start_date_str = body.get("start_date")
        end_date_str = body.get("end_date")
        if not start_date_str or not end_date_str:
            raise HTTPException(status_code=400, detail="start_date and end_date required for period absence")
        try:
            start_date = date.fromisoformat(start_date_str) if isinstance(start_date_str, str) else start_date_str
            end_date = date.fromisoformat(end_date_str) if isinstance(end_date_str, str) else end_date_str
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid date format")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")
        if start_date < date.today():
            raise HTTPException(status_code=400, detail="Absences must be in the future")

    elif absence_type == "recurring":
        rrule = body.get("rrule")
        season_id = body.get("season_id")
        if not rrule or not season_id:
            raise HTTPException(status_code=400, detail="rrule and season_id required for recurring absence")

        # Validate season exists
        season = db.query(Season).filter(Season.id == season_id).first()
        if not season:
            raise HTTPException(status_code=404, detail="Season not found")

        # Auto-set rrule_until to season end if not provided
        rrule_until_input = body.get("rrule_until")
        rrule_until = (
            date.fromisoformat(rrule_until_input)
            if isinstance(rrule_until_input, str)
            else rrule_until_input if rrule_until_input else season.end_date
        )
        if rrule_until < date.today():
            raise HTTPException(status_code=400, detail="rrule_until must be in the future")

    # Create absence
    absence = PlayerAbsence(
        player_id=player_id,
        absence_type=absence_type,
        start_date=start_date,
        end_date=end_date,
        rrule=rrule,
        rrule_until=rrule_until,
        season_id=body.get("season_id") if absence_type == "recurring" else None,
        reason=body.get("reason"),
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)

    # Apply to future events
    apply_absence_to_future_events(player_id, db)

    return {
        "id": absence.id,
        "absence_type": absence.absence_type,
        "start_date": absence.start_date,
        "end_date": absence.end_date,
        "rrule": absence.rrule,
        "rrule_until": absence.rrule_until,
        "season_id": absence.season_id,
        "reason": absence.reason,
    }


@router.delete("/players/{player_id}/absences/{absence_id}")
async def delete_player_absence(
    player_id: int,
    absence_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Delete an absence for a player."""
    # Check authorization
    absence = await require_absence_ownership_or_coach(player_id, absence_id, current_user, db)

    db.delete(absence)
    db.commit()

    return {"success": True}
