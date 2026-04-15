"""services/event_text_service.py — Shared attendance text formatter.

Used by both the Telegram bot handler (markdown=True) and the web
attendance-text endpoint (markdown=False).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.i18n import DEFAULT_LOCALE
from app.i18n import t as _t
from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam

_STATUS_ORDER = ["present", "absent", "maybe", "unknown"]
_POS_ORDER: list[str | None] = ["goalie", "defender", "center", "forward", None]
_STATUS_ICON = {"present": "✓", "absent": "✗", "unknown": "?", "maybe": "~"}


def format_attendance_body(
    players: list,
    att_by_player: dict,
    ext_rows: list,
    locale: str,
    grouped: bool = True,
    markdown: bool = False,
) -> str:
    """Render the player+external listing section of the attendance text.

    Players must have a ``_position`` attribute (str | None) set by the caller.
    Externals are integrated into their matching status section, not appended
    at the end. Position sub-headers include a player count when grouped=True.
    """
    def _bold(s: str) -> str:
        return f"*{s}*" if markdown else s

    def _italic(s: str) -> str:
        return f"_{s}_" if markdown else s

    status_header = {
        "present": _bold(_t("telegram.status_present", locale)),
        "absent": _bold(_t("telegram.status_absent", locale)),
        "maybe": _bold(_t("telegram.status_maybe", locale)),
        "unknown": _bold(_t("telegram.status_unknown", locale)),
    }
    pos_label: dict[str | None, str] = {
        "goalie": _t("telegram.pos_goalie", locale),
        "defender": _t("telegram.pos_defender", locale),
        "center": _t("telegram.pos_center", locale),
        "forward": _t("telegram.pos_forward", locale),
        None: _t("telegram.pos_other", locale),
    }

    # Group externals by status
    ext_by_status: dict[str, list] = {s: [] for s in _STATUS_ORDER}
    for ext in ext_rows:
        s = ext.status if ext.status in ext_by_status else "unknown"
        ext_by_status[s].append(ext)

    # Group players by status → position
    status_groups: dict[str, dict[str | None, list]] = {
        s: {pos: [] for pos in _POS_ORDER} for s in _STATUS_ORDER
    }
    for p in players:
        att = att_by_player.get(p.id)
        s = (att.status if att else "unknown") or "unknown"
        if s not in status_groups:
            s = "unknown"
        pos = getattr(p, "_position", None)
        if pos not in _POS_ORDER[:-1]:
            pos = None
        status_groups[s][pos].append(p)

    lines: list[str] = []
    for s in _STATUS_ORDER:
        pos_group = status_groups[s]
        exts = ext_by_status[s]
        if not any(pos_group.values()) and not exts:
            continue
        lines.append(f"\n{status_header[s]}")
        if grouped:
            for pos in _POS_ORDER:
                group = pos_group[pos]
                if not group:
                    continue
                label = f"{pos_label[pos]} ({len(group)})"
                lines.append(_italic(label))
                for p in group:
                    att = att_by_player.get(p.id)
                    line = f"  {p.full_name}"
                    if att and att.note:
                        line += f" — {att.note}"
                    lines.append(line)
        else:
            # Flat list — merge all positions and sort by name
            all_players = [p for pos in _POS_ORDER for p in pos_group[pos]]
            all_players.sort(key=lambda p: p.full_name)
            for p in all_players:
                att = att_by_player.get(p.id)
                line = f"  {p.full_name}"
                if att and att.note:
                    line += f" — {att.note}"
                lines.append(line)
        # Externals for this status, integrated here
        for ext in exts:
            ext_line = f"👤 {ext.full_name}"
            if ext.note:
                ext_line += f" — {ext.note}"
            lines.append(ext_line)

    return "\n".join(lines)


def format_attendance_text(
    db: Session,
    event: Event,
    locale: str = DEFAULT_LOCALE,
    grouped: bool = True,
    markdown: bool = False,
) -> str:
    """Render a complete shareable attendance summary for the given event.

    Includes the event header block (title, date, time, location, counts)
    followed by the full player+external listing.
    """
    def _bold(s: str) -> str:
        return f"*{s}*" if markdown else s

    # Header
    if event.event_type in ("training", "match"):
        event_type_str = _t(f"telegram.event_type_{event.event_type}", locale)
    else:
        event_type_str = _t("telegram.event_type_other", locale)

    lines: list[str] = [_bold(f"{event_type_str}: {event.title}")]
    lines.append(f"{_t('telegram.date_label', locale)}: {event.event_date}")

    if event.event_time:
        time_str = str(event.event_time)[:5]
        if event.event_end_time:
            time_str += f" - {str(event.event_end_time)[:5]}"
        lines.append(f"{_t('telegram.time_label', locale)}: {time_str}")

    if event.location:
        lines.append(f"{_t('telegram.location_label', locale)}: {event.location}")

    if event.meeting_time:
        meet = str(event.meeting_time)[:5]
        if event.meeting_location:
            meet += f" @ {event.meeting_location}"
        lines.append(f"{_t('telegram.meeting_label', locale)}: {meet}")

    # Load attendance data
    atts = db.query(Attendance).filter(Attendance.event_id == event.id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    ext_rows = (
        db.query(EventExternal)
        .filter(EventExternal.event_id == event.id)
        .order_by(EventExternal.created_at)
        .all()
    )

    # Counts line
    counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    for ext in ext_rows:
        counts[ext.status] = counts.get(ext.status, 0) + 1
    lines.append(
        f"\n{_t('telegram.attendance_label', locale)}: "
        f"✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
    )

    # Load players for this event's team+season
    if event.team_id and event.season_id:
        pt_rows = (
            db.query(PlayerTeam)
            .filter(
                PlayerTeam.team_id == event.team_id,
                PlayerTeam.season_id == event.season_id,
            )
            .all()
        )
        player_ids = {pt.player_id: pt.position for pt in pt_rows}
        players_q = (
            db.query(Player)
            .filter(Player.id.in_(player_ids.keys()), Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
        for p in players_q:
            p._position = player_ids.get(p.id)  # type: ignore[attr-defined]
    else:
        players_q = (
            db.query(Player)
            .filter(Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
        for p in players_q:
            p._position = None  # type: ignore[attr-defined]

    body = format_attendance_body(
        players_q, att_by_player, ext_rows, locale, grouped=grouped, markdown=markdown
    )
    lines.append(body)

    return "\n".join(lines)
