"""routes/calendar_view.py — Calendar month grid view."""

from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_
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


def _fmt_date(d: date) -> str:
    return d.strftime("%Y.%m.%d")


def _event_date_str(ev: Event) -> str:
    s = _fmt_date(ev.event_date)
    end = ev.event_end_date
    if end and end != ev.event_date:
        if end.year == ev.event_date.year and end.month == ev.event_date.month:
            s = f"{s}-{end.day:02d}"
        elif end.year == ev.event_date.year:
            s = f"{s}-{end.month:02d}.{end.day:02d}"
        else:
            s = f"{s}-{_fmt_date(end)}"
    return s


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
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    q = db.query(Event).filter(
        Event.event_date <= grid_end,
        or_(Event.event_end_date.is_(None), Event.event_end_date >= grid_start),
    )
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
        start = ev.event_date
        end = ev.event_end_date or start
        d = start
        while d <= end:
            events_by_date.setdefault(d, []).append(ev)
            d += timedelta(days=1)

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
            "month_start": month_start,
            "month_end": month_end,
            "MONTH_NAMES": MONTH_NAMES,
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

    from app.i18n import DEFAULT_LOCALE
    from app.i18n import t as _t

    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HTMLResponse("<p>Invalid date</p>", status_code=400)

    locale = getattr(request.state, "locale", DEFAULT_LOCALE)

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

    month_name = _t(f"calendar.{MONTH_NAMES[day.month]}", locale)
    date_header = f"{month_name} {day.day}, {day.year}"
    lines = [f'<div class="day-detail-header">{_t("calendar.events_on", locale)} {date_header}</div>']
    if not events:
        lines.append(f'<p class="day-detail-empty">{_t("calendar.no_events", locale)}</p>')
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
    lines.append(
        f'<a href="/events?date_from={day}&date_to={day}" class="day-detail-all">{_t("calendar.view_all", locale)}</a>'
    )

    return HTMLResponse("".join(lines))


@router.get("/events/export", include_in_schema=False)
async def events_export(
    request: Request,
    date_from: str = "",
    date_to: str = "",
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse

    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else date.today()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else d_from
    except ValueError:
        from fastapi.responses import HTMLResponse as _HR

        return _HR("<p>Invalid date format. Use YYYY-MM-DD.</p>", status_code=400)

    q = db.query(Event).filter(Event.event_date >= d_from, Event.event_date <= d_to)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_date.asc(), Event.event_time.asc())
    events = q.all()

    # Preload team/season names
    team_names = {t.id: t.name for t in db.query(Team).all()}
    season_names = {s.id: s.name for s in db.query(Season).all()}

    from app.i18n import DEFAULT_LOCALE
    from app.i18n import t as _t

    locale = getattr(request.state, "locale", DEFAULT_LOCALE)

    def generate():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                _t("events.date", locale),
                _t("events.time", locale),
                _t("events.meeting_time", locale),
                _t("events.title_col", locale),
                _t("events.type", locale),
                _t("events.location", locale),
                _t("events.team", locale),
                _t("events.season", locale),
            ]
        )
        for ev in events:
            ev_time = ev.event_time.strftime("%H:%M") if ev.event_time else ""
            mt = ev.meeting_time.strftime("%H:%M") if ev.meeting_time else ""
            etype = _t(f"enums.event_type.{ev.event_type}", locale) if ev.event_type else ev.event_type
            w.writerow(
                [
                    _event_date_str(ev),
                    ev_time,
                    mt,
                    ev.title,
                    etype,
                    ev.location or "",
                    team_names.get(ev.team_id or 0, ""),
                    season_names.get(ev.season_id, ""),
                ]
            )
        yield buf.getvalue()

    filename = f"events_{d_from.isoformat()}_to_{d_to.isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/events/export-text", include_in_schema=False)
async def events_export_text(
    request: Request,
    date_from: str = "",
    date_to: str = "",
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else date.today()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else d_from
    except ValueError:
        from fastapi.responses import HTMLResponse as _HR

        return _HR("<p>Invalid date format. Use YYYY-MM-DD.</p>", status_code=400)

    q = db.query(Event).filter(Event.event_date >= d_from, Event.event_date <= d_to)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_date.asc(), Event.event_time.asc())
    events = q.all()

    team_names = {t.id: t.name for t in db.query(Team).all()}
    show_team = team_id_val is None
    columns = ["Date", "Time", "Title", "Type", "Location"]
    if show_team:
        columns.append("Team")
    header = "\t".join(columns)
    lines = [header]
    for ev in events:
        display_time = ev.meeting_time or ev.event_time
        time_str = display_time.strftime("%H:%M") if display_time else "--:--"
        team_name = team_names.get(ev.team_id or 0, "") if show_team else ""
        row = [
            _event_date_str(ev),
            time_str,
            ev.title,
            ev.event_type or "",
            ev.location or "",
        ]
        if show_team:
            row.append(team_name)
        lines.append("\t".join(row))

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines))
