"""routes/schedule.py — Public event schedule (no authentication required)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
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
    season_id: int | None = None,
    team_id: int | None = None,
    db: Session = Depends(get_db),
):
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
