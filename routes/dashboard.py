"""routes/dashboard.py — Main dashboard view (role-aware)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
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


def _compute_attendance_rate(db: Session, player_id: int, active_season_id: int | None) -> tuple[int, str | None]:
    query = (
        db.query(Attendance.status, Event.event_type)
        .join(Event, Attendance.event_id == Event.id)
        .filter(Attendance.player_id == player_id)
    )
    if active_season_id:
        query = query.filter(Event.season_id == active_season_id)

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


@router.get("")
@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = date.today()
    active_season = db.query(Season).filter(Season.is_active == True).first()  # noqa: E712

    # ── Coach / Admin dashboard ─────────────────────────────────────────
    if user.is_admin or user.is_coach:
        if user.is_admin:
            team_ids: set[int] | None = None
        else:
            team_ids = get_coach_teams(user, db)

        events_q = db.query(Event)
        if active_season:
            events_q = events_q.filter(Event.season_id == active_season.id)
        if team_ids is not None:
            events_q = events_q.filter(Event.team_id.in_(team_ids))

        all_events = events_q.order_by(Event.event_date.asc()).all()
        upcoming_events = [e for e in all_events if e.event_date >= today]

        upcoming_count = len(upcoming_events)

        if upcoming_events:
            event_ids = [e.id for e in upcoming_events]
            unknown_count = (
                db.query(Attendance).filter(Attendance.event_id.in_(event_ids), Attendance.status == "unknown").count()
            )
        else:
            unknown_count = 0

        past_event_ids = [e.id for e in all_events if e.event_date < today]
        if past_event_ids:
            att_rows = db.query(Attendance.status).filter(Attendance.event_id.in_(past_event_ids)).all()
            total_att = len(att_rows)
            present_att = sum(1 for r in att_rows if r.status == "present")
            team_attendance_rate = round(present_att / total_att * 100) if total_att else 0
        else:
            team_attendance_rate = 0

        thirty_ago = today - timedelta(days=30)
        sixty_ago = today - timedelta(days=60)
        recent_ids = [e.id for e in all_events if thirty_ago <= e.event_date < today]
        older_ids = [e.id for e in all_events if sixty_ago <= e.event_date < thirty_ago]

        def _rate_for(event_id_list: list[int]) -> float:
            if not event_id_list:
                return 0.0
            rows = db.query(Attendance.status).filter(Attendance.event_id.in_(event_id_list)).all()
            if not rows:
                return 0.0
            return sum(1 for r in rows if r.status == "present") / len(rows) * 100

        recent_rate = _rate_for(recent_ids)
        older_rate = _rate_for(older_ids)
        attendance_trend = round(recent_rate - older_rate) if (recent_ids and older_ids) else None

        player_q = db.query(Player)
        if team_ids is not None:
            player_q = player_q.join(PlayerTeam, PlayerTeam.player_id == Player.id).filter(
                PlayerTeam.team_id.in_(team_ids)
            )
        active_players = player_q.filter(Player.archived_at.is_(None)).all()
        player_ids_all = [p.id for p in active_players]

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

        upcoming_events_compact = []
        for e in upcoming_events[:5]:
            atts = db.query(Attendance).filter(Attendance.event_id == e.id).all()
            total_e = len(atts)
            unknown_e = sum(1 for a in atts if a.status == "unknown")
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

        watch_list = []
        for p in active_players:
            p_att_rows = (
                db.query(Attendance)
                .filter(Attendance.player_id == p.id)
                .order_by(Attendance.event_id.desc())
                .limit(5)
                .all()
            )
            consecutive_absent = 0
            for a in sorted(p_att_rows, key=lambda x: x.event.event_date, reverse=True):
                if a.status == "absent":
                    consecutive_absent += 1
                elif a.status == "present":
                    break

            if consecutive_absent >= 3:
                watch_list.append(
                    {
                        "player_id": p.id,
                        "player_name": p.full_name,
                        "severity": "red",
                        "reason": f"Missed {consecutive_absent} events",
                    }
                )
            elif consecutive_absent >= 1:
                watch_list.append(
                    {
                        "player_id": p.id,
                        "player_name": p.full_name,
                        "severity": "yellow",
                        "reason": f"Missed {consecutive_absent} event(s)",
                    }
                )

            pt = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.player_id == p.id,
                    PlayerTeam.membership_status == "injured",
                )
                .first()
            )
            if pt and pt.injured_until:
                watch_list.append(
                    {
                        "player_id": p.id,
                        "player_name": p.full_name,
                        "severity": "green",
                        "reason": f"Injured until {pt.injured_until}",
                    }
                )

        msg_q = db.query(EventMessage).order_by(EventMessage.created_at.desc()).limit(5)
        if team_ids is not None:
            msg_q = msg_q.join(Event, EventMessage.event_id == Event.id).filter(Event.team_id.in_(team_ids))
        recent_messages = []
        for msg in msg_q.all():
            event = db.get(Event, msg.event_id)
            author = db.get(User, msg.user_id)
            author_name = (
                f"{author.first_name} {author.last_name}"
                if author and author.first_name
                else (author.username if author else "Unknown")
            )
            recent_messages.append(
                {
                    "author_name": author_name,
                    "body_truncated": msg.body[:80] + "\u2026" if len(msg.body) > 80 else msg.body,
                    "event_id": msg.event_id,
                    "event_title": event.title if event else "",
                }
            )

        return render(
            request,
            "dashboard/coach_fragment.html",
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

    # ── Player / member dashboard ────────────────────────────────────────
    player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
    my_player_id = player.id if player else None

    context: dict = {
        "user": user,
        "active_season": active_season,
        "my_player_id": my_player_id,
    }

    if my_player_id:
        rate, breakdown = _compute_attendance_rate(db, my_player_id, active_season.id if active_season else None)
        context["attendance_rate"] = rate
        context["event_type_breakdown"] = breakdown

        teams_q = db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == my_player_id)
        player_team_ids = {row[0] for row in teams_q.all()}
        next_event = None
        if player_team_ids:
            next_event = (
                db.query(Event)
                .filter(
                    Event.event_date >= today,
                    Event.team_id.in_(player_team_ids),
                )
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

        status_labels = {
            "present": "present",
            "absent": "absent",
            "maybe": "maybe",
            "unknown": "unknown",
        }
        context["status_labels"] = status_labels

        notif_q = (
            db.query(Notification)
            .filter(
                (Notification.player_id == my_player_id) | (Notification.user_id == user.id),
                Notification.is_read == False,  # noqa: E712
            )
            .order_by(Notification.created_at.desc())
        )
        context["recent_notifications"] = notif_q.limit(3).all()
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

    return render(request, "dashboard/player_fragment.html", context)
