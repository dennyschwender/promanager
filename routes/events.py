"""routes/events.py — Event CRUD + reminder sending."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.csrf import require_csrf
from app.database import get_db
from app.templates import render
from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.event_message import EventMessage
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import (
    NotAuthorized,
    check_team_access,
    get_coach_teams,
    optional_user,
    require_coach_or_admin,
    require_login,
    rt,
)
from services.attendance_service import (
    ensure_attendance_records,
    get_event_attendance_detail,
    sync_attendance_defaults,
)
from services.chat_service import author_display_name, message_to_dict
from services.email_service import send_event_reminder
from services.event_text_service import format_attendance_text
from services.notification_service import send_notifications
from services.notification_templates import TEMPLATES
from services.schedule_service import (
    advance_date as _advance_date,
)
from services.schedule_service import (
    count_future_events,
    delete_future_events,
)

router = APIRouter()


def _parse_date(val: str):
    if not val or not val.strip():
        return None
    return datetime.strptime(val.strip(), "%Y-%m-%d").date()


def _parse_time(val: str):
    if not val or not val.strip():
        return None
    return datetime.strptime(val.strip(), "%H:%M").time()


def _form_ns(
    title, event_type, event_date, event_time, event_end_time,
    location, meeting_time, meeting_location, presence_type,
    hide_attendance, description, season_id, team_id,
    is_recurring, recurrence_rule, recurrence_end_date,
) -> SimpleNamespace:
    """Build a SimpleNamespace from raw POST strings for form repopulation on error."""
    try:
        e_date = _parse_date(event_date)
    except ValueError:
        e_date = None
    try:
        e_time = _parse_time(event_time)
    except ValueError:
        e_time = None
    try:
        e_end_time = _parse_time(event_end_time)
    except ValueError:
        e_end_time = None
    try:
        m_time = _parse_time(meeting_time)
    except ValueError:
        m_time = None
    return SimpleNamespace(
        id=None,
        title=title,
        event_type=event_type,
        event_date=e_date,
        event_time=e_time,
        event_end_time=e_end_time,
        location=location or None,
        meeting_time=m_time,
        meeting_location=meeting_location or None,
        presence_type=presence_type,
        hide_attendance=bool(hide_attendance),
        description=description or None,
        season_id=int(season_id) if season_id.strip() else None,
        team_id=int(team_id) if team_id.strip() else None,
        recurrence_group_id=None,
        is_recurring=bool(is_recurring.strip()),
        recurrence_rule=recurrence_rule.strip(),
        recurrence_end_date_raw=recurrence_end_date.strip(),
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def events_list(
    request: Request,
    season_id: str | None = None,
    team_id: str | None = None,
    my_events: str | None = None,
    upcoming_page: int = 1,
    past_page: int = 1,
    user: "User | None" = Depends(optional_user),
    db: Session = Depends(get_db),
):
    import math  # noqa: PLC0415

    from models.player import Player as _Player
    PAGE_SIZE = 10
    season_id = int(season_id) if season_id and season_id.strip() else None  # type: ignore[assignment]
    team_id = int(team_id) if team_id and team_id.strip() else None  # type: ignore[assignment]
    my_events = bool(my_events) and user is not None
    today = datetime.today().date()

    q = db.query(Event)
    if season_id is not None:
        q = q.filter(Event.season_id == season_id)
    if team_id is not None:
        q = q.filter(Event.team_id == team_id)
    if my_events and user is not None:
        if user.is_admin:
            pass  # admin sees all
        elif user.is_coach:
            my_team_ids = get_coach_teams(user, db)
            q = q.filter(Event.team_id.in_(my_team_ids))
        else:
            from models.player_team import PlayerTeam as _PlayerTeam
            player = db.query(_Player).filter(
                _Player.user_id == user.id,
                _Player.archived_at.is_(None),
            ).first()
            my_team_ids = {
                row[0] for row in db.query(_PlayerTeam.team_id).filter(
                    _PlayerTeam.player_id == player.id
                ).all()
            } if player else set()
            q = q.filter(Event.team_id.in_(my_team_ids))
    all_events = q.order_by(Event.event_date.asc()).all()
    all_upcoming = [e for e in all_events if e.event_date >= today]
    all_past = sorted([e for e in all_events if e.event_date < today], key=lambda e: e.event_date, reverse=True)

    upcoming_total = math.ceil(len(all_upcoming) / PAGE_SIZE) or 1
    past_total = math.ceil(len(all_past) / PAGE_SIZE) or 1
    upcoming_page = max(1, min(upcoming_page, upcoming_total))
    past_page = max(1, min(past_page, past_total))

    upcoming = all_upcoming[(upcoming_page - 1) * PAGE_SIZE : upcoming_page * PAGE_SIZE]
    past = all_past[(past_page - 1) * PAGE_SIZE : past_page * PAGE_SIZE]

    seasons = db.query(Season).order_by(Season.name).all()
    teams = db.query(Team).order_by(Team.name).all()

    return render(
        request,
        "events/list.html",
        {
            "user": user,
            "upcoming": upcoming,
            "past": past,
            "upcoming_page": upcoming_page,
            "upcoming_total": upcoming_total,
            "past_page": past_page,
            "past_total": past_total,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id,
            "selected_team_id": team_id,
            "my_events": my_events,
            "coach_team_ids": get_coach_teams(user, db) if user and user.is_coach else set(),
            "flash": request.query_params.get("flash"),
        },
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def event_new_get(
    request: Request,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    if user.is_admin:
        teams = db.query(Team).order_by(Team.name).all()
    else:
        managed_ids = get_coach_teams(user, db)
        teams = db.query(Team).filter(Team.id.in_(managed_ids)).order_by(Team.name).all()
    return render(
        request,
        "events/form.html",
        {
            "user": user,
            "event": None,
            "is_new": True,
            "seasons": seasons,
            "teams": teams,
            "error": None,
        },
    )


@router.post("/new")
async def event_new_post(
    request: Request,
    title: str = Form(...),
    event_type: str = Form("training"),
    event_date: str = Form(...),
    event_time: str = Form(""),
    event_end_time: str = Form(""),
    location: str = Form(""),
    meeting_time: str = Form(""),
    meeting_location: str = Form(""),
    presence_type: str = Form("normal"),
    hide_attendance: str = Form(""),
    description: str = Form(""),
    season_id: str = Form(""),
    team_id: str = Form(""),
    is_recurring: str = Form(""),
    recurrence_rule: str = Form(""),
    recurrence_end_date: str = Form(""),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    if user.is_admin:
        teams = db.query(Team).order_by(Team.name).all()
    else:
        managed_ids = get_coach_teams(user, db)
        teams = db.query(Team).filter(Team.id.in_(managed_ids)).order_by(Team.name).all()

    form_ns = _form_ns(
        title, event_type, event_date, event_time, event_end_time,
        location, meeting_time, meeting_location, presence_type,
        hide_attendance, description, season_id, team_id,
        is_recurring, recurrence_rule, recurrence_end_date,
    )

    def _err(msg):
        return render(
            request,
            "events/form.html",
            {"user": user, "event": form_ns, "is_new": True, "seasons": seasons, "teams": teams, "error": msg},
            status_code=400,
        )

    parsed_team_id = int(team_id) if team_id.strip() else None
    if parsed_team_id is None:
        return _err(rt(request, "errors.field_required", field="Team"))
    if not user.is_admin:
        check_team_access(user, parsed_team_id, db)

    if not title.strip():
        return _err(rt(request, "errors.field_required", field="Event title"))

    try:
        e_date = _parse_date(event_date)
        e_time = _parse_time(event_time)
        e_end_time = _parse_time(event_end_time)
        m_time = _parse_time(meeting_time)
    except ValueError:
        return _err(rt(request, "errors.invalid_date_or_time"))

    if e_date is None:
        return _err(rt(request, "errors.field_required", field="Event date"))

    # ── Recurrence setup ──────────────────────────────────────────────────
    recurring = bool(is_recurring.strip())
    rule = recurrence_rule.strip() if recurring else None
    r_end = None
    if recurring and recurrence_end_date.strip():
        try:
            r_end = _parse_date(recurrence_end_date)
        except ValueError:
            return _err(rt(request, "errors.recurrence_end_invalid"))
    if recurring and (not rule or rule not in ("weekly", "biweekly", "monthly")):
        return _err(rt(request, "errors.recurrence_freq_invalid"))
    if recurring and r_end is None:
        # Fall back to the selected season's end date
        parsed_season_id = int(season_id) if season_id.strip() else None
        if parsed_season_id:
            season_obj = db.get(Season, parsed_season_id)
            if season_obj and season_obj.end_date:
                r_end = season_obj.end_date
        if r_end is None:
            return _err(rt(request, "errors.recurrence_end_required"))
    if recurring and r_end <= e_date:
        return _err(rt(request, "errors.recurrence_end_after_start"))

    group_id = str(uuid.uuid4()) if recurring else None
    common = dict(
        title=title.strip(),
        event_type=event_type,
        event_time=e_time,
        event_end_time=e_end_time,
        location=location.strip() or None,
        meeting_time=m_time,
        meeting_location=meeting_location.strip() or None,
        presence_type=presence_type,
        hide_attendance=bool(hide_attendance),
        description=description.strip() or None,
        season_id=int(season_id) if season_id.strip() else None,
        team_id=parsed_team_id,
        recurrence_group_id=group_id,
        recurrence_rule=rule,
    )

    # Generate all occurrences (or just one for non-recurring)
    dates_to_create = [e_date]
    if recurring:
        cur = e_date
        while True:
            cur = _advance_date(cur, rule)
            if cur > r_end:
                break
            dates_to_create.append(cur)

    first_event = None
    for occ_date in dates_to_create:
        ev = Event(event_date=occ_date, **common)
        db.add(ev)
        db.flush()  # get ev.id before commit
        ensure_attendance_records(db, ev)
        if first_event is None:
            first_event = ev

    db.commit()
    return RedirectResponse(f"/events/{first_event.id}", status_code=302)


# ---------------------------------------------------------------------------
# Notify
# ---------------------------------------------------------------------------


@router.get("/{event_id}/notify")
async def notify_get(
    event_id: int,
    request: Request,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)
    check_team_access(user, event.team_id, db, season_id=event.season_id)

    counts_q = (
        db.query(Attendance.status, func.count(Attendance.id))
        .filter(Attendance.event_id == event_id)
        .group_by(Attendance.status)
        .all()
    )
    status_counts = dict(counts_q)

    # Players with their attendance status for custom selection
    att_rows = (
        db.query(Attendance.player_id, Attendance.status)
        .filter(Attendance.event_id == event_id)
        .all()
    )
    att_by_player = {pid: status for pid, status in att_rows}
    event_players = (
        db.query(Player)
        .join(PlayerTeam, PlayerTeam.player_id == Player.id)
        .filter(
            PlayerTeam.team_id == event.team_id,
            Player.archived_at.is_(None),
        )
        .order_by(Player.last_name, Player.first_name)
        .all()
        if event.team_id else []
    )
    players_with_status = [
        {"id": p.id, "name": f"{p.first_name} {p.last_name}", "status": att_by_player.get(p.id, "unknown")}
        for p in event_players
    ]

    return render(
        request,
        "events/notify.html",
        {
            "user": user,
            "event": event,
            "templates": TEMPLATES,
            "status_counts": status_counts,
            "players_with_status": players_with_status,
        },
    )


@router.post("/{event_id}/notify")
async def notify_post(
    event_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)
    check_team_access(user, event.team_id, db, season_id=event.season_id)

    form = await request.form()
    title = (form.get("title") or "").strip()
    body = (form.get("body") or "").strip()
    tag = (form.get("tag") or "direct").strip()
    recipients_raw = form.getlist("recipients")
    channels_raw = form.getlist("channels")

    custom_player_ids: list[int] | None = None
    if "custom" in recipients_raw:
        raw_ids = form.getlist("player_ids")
        custom_player_ids = [int(x) for x in raw_ids if x.isdigit()]
        recipient_statuses = None
    else:
        recipient_statuses = None if "all" in recipients_raw else recipients_raw or None
    admin_channels = channels_raw if channels_raw else ["inapp"]

    if not title or not body:
        return RedirectResponse(f"/events/{event_id}/notify", status_code=302)

    result = send_notifications(
        event=event,
        title=title,
        body=body,
        tag=tag,
        recipient_statuses=recipient_statuses,
        admin_channels=admin_channels,
        db=db,
        background_tasks=background_tasks,
        player_ids=custom_player_ids,
    )

    return RedirectResponse(
        f"/events/{event_id}?notified={result['queued']}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{event_id}")
async def event_detail(
    event_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    if not user.is_admin:
        if user.is_coach:
            check_team_access(user, event.team_id, db, season_id=event.season_id)
        else:
            # member: must have a player with a PlayerTeam record for this event's team
            from models.player_team import PlayerTeam as _PlayerTeam
            player = db.query(Player).filter(
                Player.user_id == user.id,
                Player.archived_at.is_(None),
            ).first()
            has_access = player is not None and db.query(_PlayerTeam).filter(
                _PlayerTeam.player_id == player.id,
                _PlayerTeam.team_id == event.team_id,
            ).first() is not None
            if not has_access:
                raise NotAuthorized

    summary = get_event_attendance_detail(db, event_id)

    # Attach position to each entry and sort: position order → last_name → first_name
    _POS_ORDER = ["goalie", "defender", "center", "forward"]
    pos_by_player: dict[int, str | None] = {}
    if event.team_id and event.season_id:
        pt_rows = db.query(PlayerTeam).filter(
            PlayerTeam.team_id == event.team_id,
            PlayerTeam.season_id == event.season_id,
        ).all()
        pos_by_player = {pt.player_id: pt.position for pt in pt_rows}

    def _att_sort_key(entry: dict) -> tuple:
        return (
            entry["player"].first_name.casefold(),
            entry["player"].last_name.casefold(),
        )

    for bucket in summary:
        summary[bucket].sort(key=_att_sort_key)
        for entry in summary[bucket]:
            entry["position"] = pos_by_player.get(entry["player"].id)

    future_count = count_future_events(db, event.recurrence_group_id) if event.recurrence_group_id else 0

    atts = (
        db.query(Attendance)
        .options(joinedload(Attendance.borrowed_from_team))
        .filter(Attendance.event_id == event_id)
        .all()
    )
    att_by_player = {a.player_id: a for a in atts}

    if not (user.is_admin or user.is_coach):
        user_player_ids = {
            p.id
            for p in db.query(Player)
            .filter(
                Player.user_id == user.id,
                Player.archived_at.is_(None),
            )
            .all()
        }
    else:
        user_player_ids = set()

    externals = db.query(EventExternal).filter(EventExternal.event_id == event_id).order_by(EventExternal.created_at).all()

    chat_msgs_raw = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.created_at.asc())
        .all()
    )
    chat_messages = [
        message_to_dict(
            msg,
            author_display_name(db.get(User, msg.user_id) if msg.user_id else None),
        )
        for msg in chat_msgs_raw
    ]

    return render(
        request,
        "events/detail.html",
        {
            "user": user,
            "event": event,
            "summary": summary,
            "coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
            "future_count": future_count,
            "att_by_player": att_by_player,
            "user_player_ids": user_player_ids,
            "externals": externals,
            "chat_messages": chat_messages,
            "flash": request.query_params.get("flash"),
        },
    )


# ---------------------------------------------------------------------------
# Attendance text
# ---------------------------------------------------------------------------


@router.get("/{event_id}/attendance-text")
async def event_attendance_text(
    event_id: int,
    request: Request,
    grouped: int = 1,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    from fastapi.responses import Response

    from app.i18n import DEFAULT_LOCALE

    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404)

    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    text = format_attendance_text(db, event, locale, grouped=bool(grouped), markdown=False)
    return Response(content=text, media_type="text/plain; charset=utf-8")


# Edit
# ---------------------------------------------------------------------------


@router.get("/{event_id}/edit")
async def event_edit_get(
    event_id: int,
    request: Request,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    check_team_access(user, event.team_id, db, season_id=event.season_id)

    seasons = db.query(Season).order_by(Season.name).all()
    if user.is_admin:
        teams = db.query(Team).order_by(Team.name).all()
    else:
        managed_ids = get_coach_teams(user, db)
        teams = db.query(Team).filter(Team.id.in_(managed_ids)).order_by(Team.name).all()
    future_count = count_future_events(db, event.recurrence_group_id) if event.recurrence_group_id else 0

    return render(
        request,
        "events/form.html",
        {
            "user": user,
            "event": event,
            "seasons": seasons,
            "teams": teams,
            "error": None,
            "future_count": future_count,
            "coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
        },
    )


@router.post("/{event_id}/edit")
async def event_edit_post(
    event_id: int,
    request: Request,
    title: str = Form(...),
    event_type: str = Form("training"),
    event_date: str = Form(...),
    event_time: str = Form(""),
    event_end_time: str = Form(""),
    location: str = Form(""),
    meeting_time: str = Form(""),
    meeting_location: str = Form(""),
    presence_type: str = Form("normal"),
    hide_attendance: str = Form(""),
    description: str = Form(""),
    season_id: str = Form(""),
    team_id: str = Form(""),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    check_team_access(user, event.team_id, db, season_id=event.season_id)

    if not user.is_admin:
        team_id = str(event.team_id) if event.team_id is not None else ""

    seasons = db.query(Season).order_by(Season.name).all()
    if user.is_admin:
        teams = db.query(Team).order_by(Team.name).all()
    else:
        managed_ids = get_coach_teams(user, db)
        teams = db.query(Team).filter(Team.id.in_(managed_ids)).order_by(Team.name).all()

    if not title.strip():
        return render(
            request,
            "events/form.html",
            {
                "user": user,
                "event": event,
                "seasons": seasons,
                "teams": teams,
                "error": rt(request, "errors.field_required", field="Event title"),
            },
            status_code=400,
        )

    try:
        e_date = _parse_date(event_date)
        e_time = _parse_time(event_time)
    except ValueError:
        return render(
            request,
            "events/form.html",
            {
                "user": user,
                "event": event,
                "seasons": seasons,
                "teams": teams,
                "error": rt(request, "errors.invalid_date_or_time"),
            },
            status_code=400,
        )

    if e_date is None:
        return render(
            request,
            "events/form.html",
            {
                "user": user,
                "event": event,
                "seasons": seasons,
                "teams": teams,
                "error": rt(request, "errors.field_required", field="Event date"),
            },
            status_code=400,
        )

    try:
        e_end_time = _parse_time(event_end_time)
        m_time = _parse_time(meeting_time)
    except ValueError:
        return render(
            request,
            "events/form.html",
            {
                "user": user,
                "event": event,
                "seasons": seasons,
                "teams": teams,
                "error": rt(request, "errors.invalid_time_format"),
            },
            status_code=400,
        )

    # Capture old date to detect changes
    old_event_date = event.event_date

    event.title = title.strip()
    event.event_type = event_type
    event.event_date = e_date
    event.event_time = e_time
    event.event_end_time = e_end_time
    event.location = location.strip() or None
    event.meeting_time = m_time
    event.meeting_location = meeting_location.strip() or None
    event.presence_type = presence_type
    event.hide_attendance = bool(hide_attendance)
    event.description = description.strip() or None
    event.season_id = int(season_id) if season_id.strip() else None
    event.team_id = int(team_id) if team_id.strip() else None
    db.add(event)
    db.commit()
    # Sync existing attendance rows to the (possibly changed) presence_type
    sync_attendance_defaults(db, event)
    # Create rows for any new players added since the event was first saved
    ensure_attendance_records(db, event)
    # If event date changed, re-evaluate attendance against active absences
    if old_event_date != e_date:
        from services.absence_service import sync_attendance_to_absences_for_event
        sync_attendance_to_absences_for_event(event_id, db)
    return RedirectResponse(f"/events/{event_id}", status_code=302)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.post("/{event_id}/delete")
async def event_delete(
    event_id: int,
    request: Request,
    scope: str = Form("single"),
    _user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote  # noqa: PLC0415

    event = db.get(Event, event_id)
    if not event:
        return RedirectResponse("/events", status_code=302)

    check_team_access(_user, event.team_id, db, season_id=event.season_id)

    if scope == "future" and event.recurrence_group_id:
        n = delete_future_events(db, event.recurrence_group_id)
        db.commit()
        msg = quote(rt(request, "events.deleted_series", count=n))
        return RedirectResponse(f"/events?flash={msg}", status_code=302)

    # Default: delete single event
    db.delete(event)
    db.commit()
    msg = quote(rt(request, "events.deleted_single"))
    return RedirectResponse(f"/events?flash={msg}", status_code=302)


# ---------------------------------------------------------------------------
# Send reminders
# ---------------------------------------------------------------------------


@router.post("/{event_id}/send-reminders")
async def send_reminders(
    event_id: int,
    request: Request,
    _user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)
    check_team_access(_user, event.team_id, db, season_id=event.season_id)

    # Find all attendances with status 'unknown' that have a player email
    attendances = db.query(Attendance).filter(Attendance.event_id == event_id, Attendance.status == "unknown").all()

    sent = 0
    for att in attendances:
        player = att.player
        if player and player.email:
            ok = send_event_reminder(
                player_email=player.email,
                player_name=player.full_name,
                event_title=event.title,
                event_date=event.event_date,
                event_time=event.event_time,
                event_location=event.location or "",
            )
            if ok:
                sent += 1

    event.reminder_sent = True
    db.add(event)
    db.commit()

    return RedirectResponse(f"/events/{event_id}?reminders_sent={sent}", status_code=302)
