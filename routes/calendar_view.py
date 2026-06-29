"""routes/calendar_view.py — Calendar month grid view."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.event import Event
from models.player import Player
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import get_coach_teams, optional_user

router = APIRouter()

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTH_NAMES = [
    "",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def _filter_events_query(q, user: User | None, db: Session):
    """Apply role-based event visibility — same logic as events_list."""
    if user is None:
        return q
    if user.is_admin:
        return q
    if user.is_coach:
        my_team_ids = get_coach_teams(user, db)
        return q.filter(Event.team_id.in_(my_team_ids))
    from models.player_team import PlayerTeam

    player = (
        db.query(Player)
        .filter(
            Player.user_id == user.id,
            Player.archived_at.is_(None),
        )
        .first()
    )
    if player:
        my_team_ids = {row[0] for row in db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == player.id).all()}
        return q.filter(Event.team_id.in_(my_team_ids))
    return q.filter(Event.team_id.is_(None))


@router.get("/events/calendar", include_in_schema=False)
async def calendar_view(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    if month < 1:
        month = 1
        year -= 1
    elif month > 12:
        month = 12
        year += 1

    cal = calendar.Calendar(firstweekday=0)
    month_dates = cal.monthdatescalendar(year, month)
    grid_start = month_dates[0][0]
    grid_end = month_dates[-1][-1]

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    q = db.query(Event).filter(Event.event_date >= grid_start, Event.event_date <= grid_end)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_date.asc(), Event.event_time.asc())
    events = q.all()

    events_by_date: dict[date, list[Event]] = {}
    for ev in events:
        events_by_date.setdefault(ev.event_date, []).append(ev)

    weeks = []
    for week in month_dates:
        row = []
        for d in week:
            row.append(
                {
                    "date": d,
                    "is_current_month": d.month == month,
                    "is_today": d == today,
                    "events": events_by_date.get(d, []),
                }
            )
        weeks.append(row)

    seasons = db.query(Season).order_by(Season.name).all()
    teams = db.query(Team).order_by(Team.name).all()

    return render(
        request,
        "events/calendar.html",
        {
            "user": user,
            "weeks": weeks,
            "year": year,
            "month": month,
            "month_name": MONTH_NAMES[month],
            "prev_month": prev_month,
            "prev_year": prev_year,
            "next_month": next_month,
            "next_year": next_year,
            "weekdays": WEEKDAYS,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id_val,
            "selected_team_id": team_id_val,
            "today": today,
        },
    )


@router.get("/api/events/calendar-day", include_in_schema=False)
async def calendar_day_detail(
    request: Request,
    date_str: str,
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import HTMLResponse

    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HTMLResponse("<p>Invalid date</p>", status_code=400)

    q = db.query(Event).filter(Event.event_date == day)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_time.asc())
    events = q.all()

    lines = [f'<div class="day-detail-header">Events on {day.strftime("%B %d, %Y")}</div>']
    if not events:
        lines.append('<p class="day-detail-empty">No events on this date.</p>')
    else:
        lines.append('<ul class="day-detail-list">')
        for ev in events:
            display_time = ev.meeting_time or ev.event_time
            time_str = display_time.strftime("%H:%M ") if display_time else ""
            lines.append(
                f'<li class="day-detail-item event-type-{ev.event_type}">'
                f'<a href="/events/{ev.id}">{time_str}{ev.title}</a>'
                f"</li>"
            )
        lines.append("</ul>")
    lines.append(f'<a href="/events?date_from={day}&date_to={day}" class="day-detail-all">View all</a>')

    return HTMLResponse("".join(lines))
