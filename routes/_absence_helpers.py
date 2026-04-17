"""routes/_absence_helpers.py — Access control for absences."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from models.player_absence import PlayerAbsence
from routes._auth_helpers import require_login


async def require_absence_ownership_or_coach(
    player_id: int,
    absence_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """Check if user owns the absence (player) or coaches the player's team."""
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.user_team import UserTeam

    # Get the absence
    absence = db.query(PlayerAbsence).filter(PlayerAbsence.id == absence_id).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")

    # If admin, allow
    if current_user.is_admin:
        return absence

    # If player owns it, allow (explicit query avoids lazy-load DetachedInstanceError)
    if db.query(Player).filter(Player.user_id == current_user.id, Player.id == player_id).first():
        return absence

    # If coach, check if they manage the player's team for the relevant season
    if current_user.is_coach:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        # Check if coach manages any team the player is in (for the absence season if applicable)
        season_id = absence.season_id
        user_teams = db.query(UserTeam).filter(UserTeam.user_id == current_user.id).all()
        team_ids = {ut.team_id for ut in user_teams if season_id is None or ut.season_id == season_id}

        player_teams = db.query(PlayerTeam).filter(
            PlayerTeam.player_id == player_id,
            PlayerTeam.team_id.in_(team_ids) if team_ids else False,
        ).all()

        if player_teams:
            return absence

    raise HTTPException(status_code=403, detail="Not authorized")
