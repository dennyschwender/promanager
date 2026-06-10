"""routes/dashboard.py — Main dashboard view (role-aware)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.attendance import Attendance
from models.event import Event
from models.event_message import EventMessage
from models.notification import Notification
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.season import Season
from models.user import User
from routes._auth_helpers import get_coach_teams, require_login

router = APIRouter()

_UPCOMING_EVENTS_LIMIT = 5
_WATCH_LOOKBACK = 5
_RED_ABSENT_THRESHOLD = 3
_MSG_TRUNCATE = 80
_TREND_DAYS = 30
_TREND_COMPARE_DAYS = 60
_NOTIF_PREVIEW_LIMIT = 3
_CHAT_PREVIEW_LIMIT = 5


# ── Helpers ──────────────────────────────────────────────────────────────


def _attendance_rate(db: Session, player_id: int, season_id: int | None) -> tuple[int, str | None]:
    query = (
        db.query(Attendance.status, Event.event_type)
        .join(Event, Attendance.event_id == Event.id)
        .filter(Attendance.player_id == player_id)
    )
    if season_id:
        query = query.filter(Event.season_id == season_id)

    rows = query.all()
    if not rows:
        return 0, None

    total = len(rows)
    present = sum(1 for r in rows if r.status == "present")
    rate = round(present / total * 100) if total else 0

    type_breakdown: dict = {}
    for r in rows:
        type_breakdown.setdefault(r.event_type, [0, 0])
        type_breakdown[r.event_type][0] += 1
        if r.status == "present":
            type_breakdown[r.event_type][1] += 1

    breakdown_str = " \u00b7 ".join(
        f"{etype.capitalize()} {round(cnt[1] / cnt[0] * 100) if cnt[0] else 0}%"
        for etype, cnt in sorted(type_breakdown.items())
    )
    return rate, breakdown_str


def _rate_for(db: Session, event_ids: list[int]) -> float:
    """Return present/total rate for a set of event IDs. 0 if none."""
    if not event_ids:
        return 0.0
    result = (
        db.query(func.count(Attendance.id).filter(Attendance.status == "present"), func.count(Attendance.id))
        .filter(Attendance.event_id.in_(event_ids))
        .first()
    )
    if not result or not result[1]:
        return 0.0
    return result[0] / result[1] * 100


# ── Route ────────────────────────────────────────────────────────────────


@router.get("")
@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = date.today()
    active_season = db.query(Season).filter(Season.is_active.is_(True)).first()

    # ── Coach / Admin ──────────────────────────────────────────────────
    if user.is_admin or user.is_coach:
        team_ids: set[int] | None = None if user.is_admin else get_coach_teams(user, db)

        events_q = db.query(Event)
        if active_season:
            events_q = events_q.filter(Event.season_id == active_season.id)
        if team_ids is not None:
            events_q = events_q.filter(Event.team_id.in_(team_ids))

        all_events = events_q.order_by(Event.event_date.asc()).all()
        upcoming_events = [e for e in all_events if e.event_date >= today]
        upcoming_event_ids = [e.id for e in upcoming_events]
        past_event_ids = [e.id for e in all_events if e.event_date < today]

        upcoming_count = len(upcoming_events)

        # Pending count
        unknown_count = 0
        if upcoming_event_ids:
            unknown_count = (
                db.query(Attendance)
                .filter(Attendance.event_id.in_(upcoming_event_ids), Attendance.status == "unknown")
                .count()
            )

        # Team attendance rate (past events)
        team_attendance_rate = 0
        if past_event_ids:
            att_rows = db.query(Attendance.status).filter(Attendance.event_id.in_(past_event_ids)).all()
            total_att = len(att_rows)
            present_att = sum(1 for r in att_rows if r.status == "present")
            team_attendance_rate = round(present_att / total_att * 100) if total_att else 0

        # Trend: compare recent window vs older window
        thirty_ago = today - timedelta(days=_TREND_DAYS)
        sixty_ago = today - timedelta(days=_TREND_COMPARE_DAYS)
        recent_ids = [e.id for e in all_events if thirty_ago <= e.event_date < today]
        older_ids = [e.id for e in all_events if sixty_ago <= e.event_date < thirty_ago]

        recent_rate = _rate_for(db, recent_ids)
        older_rate = _rate_for(db, older_ids)
        attendance_trend = (
            round(recent_rate - older_rate) if (recent_ids and older_ids and (recent_ids != older_ids)) else None
        )

        # Player roster
        player_q = db.query(Player)
        if team_ids is not None:
            player_q = player_q.join(PlayerTeam, PlayerTeam.player_id == Player.id).filter(
                PlayerTeam.team_id.in_(team_ids)
            )
        active_players = player_q.filter(Player.archived_at.is_(None)).all()
        player_ids_all = [p.id for p in active_players]

        # Injured/absence counts
        injured_count = 0
        absence_count = 0
        if player_ids_all:
            injured_count = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.player_id.in_(player_ids_all),
                    PlayerTeam.membership_status == "injured",
                )
                .count()
            )
            absence_count = (
                db.query(PlayerAbsence)
                .filter(
                    PlayerAbsence.player_id.in_(player_ids_all),
                    PlayerAbsence.start_date <= today,
                    PlayerAbsence.end_date >= today,
                )
                .count()
            )
        injured_absent_count = injured_count + absence_count

        # Compact upcoming events (batch attendance query)
        upcoming_events_compact = []
        top_event_ids = [e.id for e in upcoming_events[:_UPCOMING_EVENTS_LIMIT]]
        if top_event_ids:
            att_rows = (
                db.query(Attendance.event_id, Attendance.status).filter(Attendance.event_id.in_(top_event_ids)).all()
            )
            att_by_event: dict[int, list[str]] = {}
            for a in att_rows:
                att_by_event.setdefault(a.event_id, []).append(a.status)

            for e in upcoming_events[:_UPCOMING_EVENTS_LIMIT]:
                statuses = att_by_event.get(e.id, [])
                total_e = len(statuses)
                unknown_e = sum(1 for s in statuses if s == "unknown")
                days_diff = (e.event_date - today).days
                if days_diff == 0:
                    label = "Today"
                elif days_diff == 1:
                    label = "Tomorrow"
                else:
                    label = e.event_date.strftime("%a %d")
                upcoming_events_compact.append(
                    {
                        "id": e.id,
                        "title": e.title,
                        "date_label": label,
                        "unknown_count": unknown_e,
                        "total_count": total_e,
                    }
                )

        # Watch list (batch queries)
        watch_lookup: set[int] = set()
        watch_list = []

        # Batch: consecutive absences — query last N attendance records per player
        if player_ids_all:
            subq = (
                db.query(
                    Attendance.player_id,
                    Attendance.status,
                    Event.event_date,
                    func.row_number()
                    .over(partition_by=Attendance.player_id, order_by=Event.event_date.desc())
                    .label("rn"),
                )
                .join(Event, Attendance.event_id == Event.id)
                .filter(Attendance.player_id.in_(player_ids_all))
                .subquery()
            )
            recent_atts = (
                db.query(subq)
                .filter(subq.c.rn <= _WATCH_LOOKBACK)
                .order_by(subq.c.player_id, subq.c.event_date.desc())
                .all()
            )

            player_absent_count: dict[int, int] = {}
            for row in recent_atts:
                if row.player_id not in player_absent_count:
                    player_absent_count[row.player_id] = 0
                if row.status == "absent":
                    player_absent_count[row.player_id] += 1
                elif row.status == "present":
                    player_absent_count[row.player_id] = -999  # mark as seen

            for p in active_players:
                count = player_absent_count.get(p.id, 0)
                if count < 0:
                    continue  # has recent present, not a concern
                if count >= _RED_ABSENT_THRESHOLD:
                    watch_lookup.add(p.id)
                    watch_list.append(
                        {
                            "player_id": p.id,
                            "player_name": p.full_name,
                            "severity": "red",
                            "reason": f"Missed {count} events",
                        }
                    )
                elif count >= 1:
                    watch_lookup.add(p.id)
                    watch_list.append(
                        {
                            "player_id": p.id,
                            "player_name": p.full_name,
                            "severity": "yellow",
                            "reason": f"Missed {count} event(s)",
                        }
                    )

            # Batch: injured players
            injured_pts = (
                db.query(PlayerTeam.player_id, PlayerTeam.injured_until)
                .filter(
                    PlayerTeam.player_id.in_(player_ids_all),
                    PlayerTeam.membership_status == "injured",
                    PlayerTeam.injured_until.isnot(None),
                )
                .all()
            )
            for row in injured_pts:
                if row.player_id not in watch_lookup:
                    p = next((x for x in active_players if x.id == row.player_id), None)
                    if p:
                        watch_list.append(
                            {
                                "player_id": p.id,
                                "player_name": p.full_name,
                                "severity": "green",
                                "reason": f"Injured until {row.injured_until}",
                            }
                        )

        # Recent chat (joined query)
        msg_q = (
            db.query(EventMessage, Event.title, User.first_name, User.last_name, User.username)
            .join(Event, EventMessage.event_id == Event.id)
            .outerjoin(User, EventMessage.user_id == User.id)
            .order_by(EventMessage.created_at.desc())
        )
        if team_ids is not None:
            msg_q = msg_q.filter(Event.team_id.in_(team_ids))
        msg_q = msg_q.limit(_CHAT_PREVIEW_LIMIT)
        recent_messages = []
        for msg, event_title, fn, ln, un in msg_q.all():
            author_name = f"{fn} {ln}" if fn else (un or "Unknown")
            recent_messages.append(
                {
                    "author_name": author_name,
                    "body_truncated": msg.body[:_MSG_TRUNCATE] + "\u2026"
                    if len(msg.body) > _MSG_TRUNCATE
                    else msg.body,
                    "event_id": msg.event_id,
                    "event_title": event_title or "",
                }
            )

        return render(
            request,
            "dashboard/index.html",
            {
                "user": user,
                "active_season": active_season,
                "team_attendance_rate": team_attendance_rate,
                "attendance_trend": attendance_trend,
                "unknown_count": unknown_count,
                "upcoming_count": upcoming_count,
                "injured_absent_count": injured_absent_count,
                "injured_count": injured_count,
                "absence_count": absence_count,
                "upcoming_events_compact": upcoming_events_compact,
                "watch_list": watch_list,
                "recent_messages": recent_messages,
            },
        )

    # ── Player / member ─────────────────────────────────────────────────
    player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
    my_player_id = player.id if player else None

    context: dict = {
        "user": user,
        "active_season": active_season,
        "my_player_id": my_player_id,
        "status_labels": {
            "present": "Present",
            "absent": "Absent",
            "maybe": "Maybe",
            "unknown": "Unknown",
        },
    }

    if my_player_id:
        rate, breakdown = _attendance_rate(db, my_player_id, active_season.id if active_season else None)
        context["attendance_rate"] = rate
        context["event_type_breakdown"] = breakdown

        player_team_ids = {
            row[0] for row in db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == my_player_id).all()
        }
        next_event = None
        if player_team_ids:
            next_event = (
                db.query(Event)
                .filter(Event.event_date >= today, Event.team_id.in_(player_team_ids))
                .order_by(Event.event_date.asc())
                .first()
            )
        context["next_event"] = next_event
        if next_event:
            att = (
                db.query(Attendance)
                .filter(Attendance.event_id == next_event.id, Attendance.player_id == my_player_id)
                .first()
            )
            context["my_next_status"] = att.status if att else "unknown"
            context["my_next_note"] = att.note if att and att.note else ""
        else:
            context["my_next_status"] = "unknown"
            context["my_next_note"] = ""

        notif_q = (
            db.query(Notification)
            .filter(
                (Notification.player_id == my_player_id) | (Notification.user_id == user.id),
                Notification.is_read.is_(False),
            )
            .order_by(Notification.created_at.desc())
        )
        context["recent_notifications"] = notif_q.limit(_NOTIF_PREVIEW_LIMIT).all()
        context["unread_count"] = notif_q.count()

        context["active_absences"] = (
            db.query(PlayerAbsence)
            .filter(
                PlayerAbsence.player_id == my_player_id,
                PlayerAbsence.end_date >= today,
            )
            .order_by(PlayerAbsence.start_date.asc())
            .all()
        )

    return render(request, "dashboard/index.html", context)
