"""routes/reports.py — Season and player attendance reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.event import Event
from models.player import Player
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import require_login
from services.attendance_service import (
    get_event_attendance_stats,
    get_matrix_attendance_stats,
    get_player_attendance_history,
    get_season_attendance_stats,
)

router = APIRouter()

_EVENT_TYPES = ("training", "match", "other")


def _season_teams(db: Session, season_id: int) -> list[Team]:
    """Teams that have at least one event in this season."""
    team_ids = (
        db.query(Event.team_id)
        .filter(Event.season_id == season_id, Event.team_id.isnot(None))
        .distinct()
        .all()
    )
    ids = [r[0] for r in team_ids]
    if not ids:
        return []
    return db.query(Team).filter(Team.id.in_(ids)).order_by(Team.name).all()


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
                return RedirectResponse(f"/reports/season/{season.id}?team_id={first_team_id}&hide_future=1", status_code=302)
        return RedirectResponse(f"/reports/season/{season.id}?hide_future=1", status_code=302)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Season report — attendance stats per player
# ---------------------------------------------------------------------------


@router.get("/season/{season_id}")
async def report_season(
    season_id: int,
    request: Request,
    team_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    hide_future: str | None = Query(default=None),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    team_id_int = int(team_id) if team_id else None
    event_type_val = event_type if event_type in _EVENT_TYPES else None
    hide_future_bool = hide_future == "1"

    all_seasons = db.query(Season).order_by(Season.name).all()
    teams = _season_teams(db, season_id)

    if user.is_coach and not user.is_admin:
        from models.player_team import PlayerTeam as _PT  # noqa: PLC0415
        from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

        coach_team_ids = get_coach_teams(user, db, season_id=season_id)
        coach_player_ids: set[int] | None = (
            {
                row.player_id
                for row in db.query(_PT)
                .filter(_PT.team_id.in_(coach_team_ids), _PT.season_id == season_id)
                .all()
            }
            if coach_team_ids
            else set()
        )
        # Coaches can only filter within their own teams
        if team_id_int and team_id_int not in coach_team_ids:
            team_id_int = None
    else:
        coach_player_ids = None

    stats = get_season_attendance_stats(db, season_id, team_id=team_id_int, event_type=event_type_val, hide_future=hide_future_bool)

    return render(
        request,
        "reports/season.html",
        {
            "user": user,
            "season": season,
            "stats": stats,
            "all_seasons": all_seasons,
            "teams": teams,
            "coach_player_ids": coach_player_ids,
            "selected_team_id": team_id_int,
            "selected_event_type": event_type_val or "",
            "hide_future": "1" if hide_future_bool else "",
        },
    )


# ---------------------------------------------------------------------------
# Event report — attendance counts per event
# ---------------------------------------------------------------------------


@router.get("/event/{season_id}")
async def report_event(
    season_id: int,
    request: Request,
    team_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    hide_future: str | None = Query(default=None),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    team_id_int = int(team_id) if team_id else None
    event_type_val = event_type if event_type in _EVENT_TYPES else None
    hide_future_bool = hide_future == "1"

    all_seasons = db.query(Season).order_by(Season.name).all()
    teams = _season_teams(db, season_id)

    allowed_team_ids: set[int] | None = None
    if user.is_coach and not user.is_admin:
        from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

        allowed_team_ids = get_coach_teams(user, db, season_id=season_id)
        if team_id_int and team_id_int not in allowed_team_ids:
            team_id_int = None

    stats = get_event_attendance_stats(
        db, season_id,
        team_id=team_id_int,
        event_type=event_type_val,
        hide_future=hide_future_bool,
        allowed_team_ids=allowed_team_ids,
    )

    return render(
        request,
        "reports/event.html",
        {
            "user": user,
            "season": season,
            "stats": stats,
            "all_seasons": all_seasons,
            "teams": teams,
            "selected_team_id": team_id_int,
            "selected_event_type": event_type_val or "",
            "hide_future": "1" if hide_future_bool else "",
        },
    )


# ---------------------------------------------------------------------------
# Matrix report — players × events grid
# ---------------------------------------------------------------------------


@router.get("/matrix/{season_id}")
async def report_matrix(
    season_id: int,
    request: Request,
    team_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    from datetime import date as _date  # noqa: PLC0415

    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    team_id_int = int(team_id) if team_id else None
    event_type_val = event_type if event_type in _EVENT_TYPES else None

    def _parse_date(s: str | None) -> _date | None:
        if not s:
            return None
        try:
            return _date.fromisoformat(s)
        except ValueError:
            return None

    date_from_val = _parse_date(date_from)
    date_to_val = _parse_date(date_to)

    all_seasons = db.query(Season).order_by(Season.name).all()
    teams = _season_teams(db, season_id)

    allowed_team_ids: set[int] | None = None
    if user.is_coach and not user.is_admin:
        from routes._auth_helpers import get_coach_teams  # noqa: PLC0415

        allowed_team_ids = get_coach_teams(user, db, season_id=season_id)
        if team_id_int and team_id_int not in allowed_team_ids:
            team_id_int = None

    matrix = get_matrix_attendance_stats(
        db, season_id,
        team_id=team_id_int,
        event_type=event_type_val,
        date_from=date_from_val,
        date_to=date_to_val,
        allowed_team_ids=allowed_team_ids,
    )

    return render(
        request,
        "reports/matrix.html",
        {
            "user": user,
            "season": season,
            "all_seasons": all_seasons,
            "teams": teams,
            "matrix": matrix,
            "selected_team_id": team_id_int,
            "selected_event_type": event_type_val or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
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
