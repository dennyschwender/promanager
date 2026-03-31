"""routes/dashboard.py — Main dashboard view."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.attendance import Attendance
from models.event import Event
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import get_coach_teams, require_login

router = APIRouter()


@router.get("")
@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = date.today()
    horizon = today + timedelta(days=30)

    # Active season
    active_season = db.query(Season).filter(Season.is_active == True).first()  # noqa: E712

    # Upcoming events (next 30 days) for the active season
    events_q = db.query(Event).filter(
        Event.event_date >= today,
        Event.event_date <= horizon,
    )
    if active_season:
        events_q = events_q.filter(Event.season_id == active_season.id)
    if not user.is_admin:
        team_ids = get_coach_teams(user, db)
        events_q = events_q.filter(Event.team_id.in_(team_ids))
    upcoming_events = events_q.order_by(Event.event_date.asc()).all()

    upcoming_count = len(upcoming_events)
    top_events = upcoming_events[:5]

    # Count players with unknown attendance across upcoming events
    unknown_count = 0
    if upcoming_events:
        event_ids = [e.id for e in upcoming_events]
        unknown_count = (
            db.query(Attendance)
            .filter(
                Attendance.event_id.in_(event_ids),
                Attendance.status == "unknown",
            )
            .count()
        )

    # Admin extras
    all_teams = []
    all_seasons = []
    if user.is_admin:
        all_teams = db.query(Team).order_by(Team.name).all()
        all_seasons = db.query(Season).order_by(Season.name).all()

    return render(
        request,
        "dashboard/index.html",
        {
            "user": user,
            "active_season": active_season,
            "upcoming_count": upcoming_count,
            "unknown_count": unknown_count,
            "top_events": top_events,
            "all_teams": all_teams,
            "all_seasons": all_seasons,
        },
    )
