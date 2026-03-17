"""routes/schedule.py — Public event schedule (no authentication required)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.event import Event
from models.season import Season
from models.team import Team

router = APIRouter()


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def schedule_page(
    request: Request,
    season_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    season_id_int: int | None = int(season_id) if season_id and season_id.strip() else None
    team_id_int: int | None = int(team_id) if team_id and team_id.strip() else None
    season_id = season_id_int  # type: ignore[assignment]
    team_id = team_id_int  # type: ignore[assignment]

    seasons = db.query(Season).order_by(Season.start_date.desc()).all()
    teams = db.query(Team).order_by(Team.name).all()

    # Default to active season if none selected
    if not season_id:
        active = db.query(Season).filter(Season.is_active.is_(True)).first()
        if active:
            season_id = active.id

    q = db.query(Event).filter(Event.event_date >= date.today())
    if season_id:
        q = q.filter(Event.season_id == season_id)
    if team_id:
        q = q.filter(Event.team_id == team_id)
    events = q.order_by(Event.event_date, Event.event_time).all()

    return render(
        request,
        "schedule/index.html",
        {
            "events": events,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id,
            "selected_team_id": team_id,
        },
    )
