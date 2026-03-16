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
    if active:
        return RedirectResponse(f"/reports/season/{active.id}", status_code=302)
    first = db.query(Season).order_by(Season.name).first()
    if first:
        return RedirectResponse(f"/reports/season/{first.id}", status_code=302)
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

    return render(
        request,
        "reports/season.html",
        {
            "user": user,
            "season": season,
            "stats": stats,
            "all_seasons": all_seasons,
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

    # Non-admins may only view their own reports
    if not user.is_admin and player.user_id != user.id:
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
