"""routes/schedule.py — Public event schedule (no authentication required)."""

from __future__ import annotations

from datetime import datetime

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
    season_id: str | None = None,
    team_id: str | None = None,
    db: Session = Depends(get_db),
):
    season_id = int(season_id) if season_id and season_id.strip() else None  # type: ignore[assignment]
    team_id = int(team_id) if team_id and team_id.strip() else None  # type: ignore[assignment]
    today = datetime.today().date()

    q = db.query(Event)
    if season_id is not None:
        q = q.filter(Event.season_id == season_id)
    if team_id is not None:
        q = q.filter(Event.team_id == team_id)

    all_events = q.order_by(Event.event_date.desc()).all()
    upcoming = [e for e in all_events if e.event_date >= today]
    past = [e for e in all_events if e.event_date < today]

    seasons = db.query(Season).order_by(Season.name).all()
    teams = db.query(Team).order_by(Team.name).all()

    return render(
        request,
        "events/list.html",
        {
            "user": getattr(request.state, "user", None),
            "upcoming": upcoming,
            "past": past,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id,
            "selected_team_id": team_id,
            "coach_team_ids": set(),
        },
    )
