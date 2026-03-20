"""routes/reports.py — Season and player attendance reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.player import Player
from models.season import Season
from models.user import User
from routes._auth_helpers import require_login
from services.attendance_service import (
    get_player_attendance_history,
    get_season_attendance_stats,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Reports index — redirect to active season or first available
# ---------------------------------------------------------------------------


@router.get("")
async def reports_index(
    request: Request,
    _user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    active = db.query(Season).filter(Season.is_active.is_(True)).first()
    season = active or db.query(Season).order_by(Season.name).first()
    if season:
        if _user.is_coach and not _user.is_admin:
            from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

            managed = get_coach_teams(_user, db)
            if managed:
                first_team_id = next(iter(sorted(managed)))
                return RedirectResponse(f"/reports/season/{season.id}?team_id={first_team_id}", status_code=302)
        return RedirectResponse(f"/reports/season/{season.id}", status_code=302)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Season report — attendance stats per player
# ---------------------------------------------------------------------------


@router.get("/season/{season_id}")
async def report_season(
    season_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    stats = get_season_attendance_stats(db, season_id)
    all_seasons = db.query(Season).order_by(Season.name).all()

    if user.is_coach and not user.is_admin:
        from models.player_team import PlayerTeam as _PT  # noqa: PLC0415
        from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

        coach_team_ids = get_coach_teams(user, db, season_id=season_id)
        # Build set of player IDs on any of the coach's teams this season
        coach_player_ids: set[int] | None = (
            {
                row.player_id
                for row in db.query(_PT)
                .filter(
                    _PT.team_id.in_(coach_team_ids),
                    _PT.season_id == season_id,
                )
                .all()
            }
            if coach_team_ids
            else set()
        )
    else:
        coach_player_ids = None

    return render(
        request,
        "reports/season.html",
        {
            "user": user,
            "season": season,
            "stats": stats,
            "all_seasons": all_seasons,
            "coach_player_ids": coach_player_ids,
        },
    )


# ---------------------------------------------------------------------------
# Player report — full attendance history
# ---------------------------------------------------------------------------


@router.get("/player/{player_id}")
async def report_player(
    player_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    # Non-admins access control
    if not user.is_admin:
        if user.is_coach:
            from models.player_team import PlayerTeam as _PT  # noqa: PLC0415
            from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

            managed_ids = get_coach_teams(user, db)
            player_team_ids = {row.team_id for row in db.query(_PT).filter(_PT.player_id == player.id).all()}
            if not managed_ids.intersection(player_team_ids):
                return RedirectResponse("/dashboard", status_code=302)
        elif player.user_id != user.id:
            return RedirectResponse("/dashboard", status_code=302)

    history = get_player_attendance_history(db, player_id)

    return render(
        request,
        "reports/player.html",
        {
            "user": user,
            "player": player,
            "history": history,
        },
    )
