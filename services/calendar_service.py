# services/calendar_service.py
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.event import Event
from models.player_team import PlayerTeam
from models.user import User
from models.user_team import UserTeam


def generate_token() -> str:
    return secrets.token_hex(32)


def fold_line(line: str) -> str:
    """RFC 5545 line folding: max 75 octets, continuation lines start with space."""
    if len(line) <= 75:
        return line
    parts = []
    while len(line) > 75:
        parts.append(line[:75])
        line = " " + line[75:]
    parts.append(line)
    return "\r\n".join(parts)


def _vevent(uid: str, summary: str, dtstart: str, dtend: str, location: str | None, dtstamp: str) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        fold_line(f"UID:{uid}"),
        fold_line(f"SUMMARY:{summary}"),
        dtstart,
        dtend,
    ]
    if location:
        lines.append(fold_line(f"LOCATION:{location}"))
    lines.append(f"DTSTAMP:{dtstamp}")
    lines.append("END:VEVENT")
    return lines


def _get_events_for_user(user: User, db: Session) -> list[Event]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)

    if user.is_admin:
        return (
            db.query(Event)
            .filter(Event.event_date >= cutoff)
            .order_by(Event.event_date)
            .all()
        )

    if user.is_coach:
        team_ids = [ut.team_id for ut in db.query(UserTeam).filter(UserTeam.user_id == user.id).all()]
        if not team_ids:
            return []
        return (
            db.query(Event)
            .filter(Event.team_id.in_(team_ids), Event.event_date >= cutoff)
            .order_by(Event.event_date)
            .all()
        )

    # member
    from models.player import Player  # noqa: PLC0415

    player = db.query(Player).filter(Player.user_id == user.id, Player.is_active.is_(True)).first()
    if not player:
        return []
    team_ids = [pt.team_id for pt in db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id).all()]
    if not team_ids:
        return []
    return (
        db.query(Event)
        .filter(Event.team_id.in_(team_ids), Event.event_date >= cutoff)
        .order_by(Event.event_date)
        .all()
    )


def build_ical_feed(user: User, db: Session, app_url: str, tz: str) -> str:
    events = _get_events_for_user(user, db)

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ProManager//ProManager//EN",
        fold_line("X-WR-CALNAME:ProManager"),
        "X-WR-CALDESC:ProManager team events",
        "CALSCALE:GREGORIAN",
    ]

    for event in events:
        created_utc = event.created_at.strftime("%Y%m%dT%H%M%SZ") if event.created_at else "19700101T000000Z"
        d = event.event_date

        if event.event_time:
            t_start = event.event_time
            t_end = event.event_end_time or (
                datetime.combine(d, t_start) + timedelta(hours=1)
            ).time()
            dtstart = f"DTSTART;TZID={tz}:{d.strftime('%Y%m%d')}T{t_start.strftime('%H%M%S')}"
            dtend = f"DTEND;TZID={tz}:{d.strftime('%Y%m%d')}T{t_end.strftime('%H%M%S')}"
        else:
            next_day = d + timedelta(days=1)
            dtstart = f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}"
            dtend = f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}"

        lines.extend(
            _vevent(
                uid=f"{event.id}@promanager",
                summary=event.title,
                dtstart=dtstart,
                dtend=dtend,
                location=event.location,
                dtstamp=created_utc,
            )
        )

        # Meeting-point VEVENT
        if event.meeting_time and event.event_time:
            m_dtstart = f"DTSTART;TZID={tz}:{d.strftime('%Y%m%d')}T{event.meeting_time.strftime('%H%M%S')}"
            m_dtend = f"DTEND;TZID={tz}:{d.strftime('%Y%m%d')}T{event.event_time.strftime('%H%M%S')}"
            lines.extend(
                _vevent(
                    uid=f"{event.id}-meet@promanager",
                    summary=f"Meet: {event.title}",
                    dtstart=m_dtstart,
                    dtend=m_dtend,
                    location=event.meeting_location or event.location,
                    dtstamp=created_utc,
                )
            )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
