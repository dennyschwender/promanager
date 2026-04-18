"""services/attendance_service.py — Attendance business logic."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.player_team import PlayerTeam

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def get_or_create_attendance(db: Session, event_id: int, player_id: int) -> Attendance:
    """Return the existing Attendance row or create it with status 'unknown'."""
    att = db.query(Attendance).filter(Attendance.event_id == event_id, Attendance.player_id == player_id).first()
    if att is None:
        att = Attendance(event_id=event_id, player_id=player_id, status="unknown")
        db.add(att)
        db.commit()
        db.refresh(att)
    return att


def set_attendance(
    db: Session,
    event_id: int,
    player_id: int,
    status: str,
    note: str | None = None,
) -> Attendance:
    """Set (or create) the attendance record for a player/event pair.

    Pass `note` to update the note; omit it (or pass None) to preserve the existing note.
    Pass `note=""` to explicitly clear it.
    """
    att = get_or_create_attendance(db, event_id, player_id)
    att.status = status
    if note is not None:
        att.note = note or None
    att.updated_at = datetime.now(timezone.utc)
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


# ---------------------------------------------------------------------------
# Summary / stats helpers
# ---------------------------------------------------------------------------


def get_event_attendance_summary(db: Session, event_id: int) -> dict:
    """Return dict keyed by status, each value a list of Player objects."""
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    attendances = (
        db.query(Attendance).options(joinedload(Attendance.player)).filter(Attendance.event_id == event_id).all()
    )
    summary: dict[str, list[Player]] = {
        "present": [],
        "absent": [],
        "maybe": [],
        "unknown": [],
    }
    for att in attendances:
        bucket = att.status if att.status in summary else "unknown"
        if att.player:
            summary[bucket].append(att.player)
    return summary


def get_event_attendance_detail(db: Session, event_id: int) -> dict:
    """Return dict keyed by status, each value a list of {player, note} dicts.

    Unlike get_event_attendance_summary, this preserves the attendance note
    so it can be surfaced in the event detail UI.
    """
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    attendances = (
        db.query(Attendance).options(joinedload(Attendance.player)).filter(Attendance.event_id == event_id).all()
    )
    detail: dict[str, list[dict]] = {
        "present": [],
        "absent": [],
        "maybe": [],
        "unknown": [],
    }
    for att in attendances:
        bucket = att.status if att.status in detail else "unknown"
        if att.player:
            detail[bucket].append({"player": att.player, "note": att.note or ""})
    return detail


def get_season_attendance_stats(
    db: Session,
    season_id: int,
    team_id: int | None = None,
    event_type: str | None = None,
    hide_future: bool = False,
) -> list[dict]:
    """Per-player stats for an entire season.

    Returns a list of dicts:
        {player, present_count, absent_count, maybe_count, unknown_count, total_events}
    """
    # Find all events for this season (with optional filters)
    q = db.query(Event).filter(Event.season_id == season_id)
    if team_id is not None:
        q = q.filter(Event.team_id == team_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if hide_future:
        q = q.filter(Event.event_date <= date.today())
    events = q.all()
    event_ids = [e.id for e in events]
    total_events = len(event_ids)

    if not event_ids:
        return []

    # Collect all attendances for those events (eager-load player to avoid N+1)
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    attendances = (
        db.query(Attendance).options(joinedload(Attendance.player)).filter(Attendance.event_id.in_(event_ids)).all()
    )

    # Group by player
    player_map: dict[int, dict] = {}
    for att in attendances:
        if att.player_id not in player_map:
            player_map[att.player_id] = {
                "player": att.player,
                "present_count": 0,
                "absent_count": 0,
                "maybe_count": 0,
                "unknown_count": 0,
                "total_events": total_events,
            }
        entry = player_map[att.player_id]
        key = f"{att.status}_count"
        if key in entry:
            entry[key] += 1

    return sorted(
        player_map.values(),
        key=lambda x: x["player"].last_name if x["player"] else "",
    )


def get_event_attendance_stats(
    db: Session,
    season_id: int,
    team_id: int | None = None,
    event_type: str | None = None,
    hide_future: bool = False,
    allowed_team_ids: set[int] | None = None,
) -> list[dict]:
    """Per-event attendance counts for a season.

    Returns a list of dicts sorted by event_date asc:
        {event, present_count, absent_count, maybe_count, unknown_count, total_players}
    """
    q = db.query(Event).filter(Event.season_id == season_id)
    if team_id is not None:
        q = q.filter(Event.team_id == team_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if hide_future:
        q = q.filter(Event.event_date <= date.today())
    if allowed_team_ids is not None:
        q = q.filter(Event.team_id.in_(allowed_team_ids))
    events = q.order_by(Event.event_date.asc()).all()

    if not events:
        return []

    event_ids = [e.id for e in events]
    attendances = db.query(Attendance).filter(Attendance.event_id.in_(event_ids)).all()

    counts: dict[int, dict] = {e.id: {"present": 0, "absent": 0, "maybe": 0, "unknown": 0} for e in events}
    for att in attendances:
        bucket = att.status if att.status in counts[att.event_id] else "unknown"
        counts[att.event_id][bucket] += 1

    results = []
    for event in events:
        c = counts[event.id]
        total = c["present"] + c["absent"] + c["maybe"] + c["unknown"]
        results.append({
            "event": event,
            "present_count": c["present"],
            "absent_count": c["absent"],
            "maybe_count": c["maybe"],
            "unknown_count": c["unknown"],
            "total_players": total,
        })
    return results


def get_matrix_attendance_stats(
    db: Session,
    season_id: int,
    team_id: int | None = None,
    event_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    allowed_team_ids: set[int] | None = None,
) -> dict:
    """Matrix report: players × events.

    Returns:
        {
            "events": [Event, ...],           # sorted by date asc
            "rows": [
                {
                    "player": Player,
                    "statuses": {event_id: status_str, ...},  # missing = no record
                    "present_count": int,
                    "total": int,
                },
                ...
            ],
        }
    """
    q = db.query(Event).filter(Event.season_id == season_id)
    if team_id is not None:
        q = q.filter(Event.team_id == team_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if date_from:
        q = q.filter(Event.event_date >= date_from)
    if date_to:
        q = q.filter(Event.event_date <= date_to)
    if allowed_team_ids is not None:
        q = q.filter(Event.team_id.in_(allowed_team_ids))
    events = q.order_by(Event.event_date.asc()).all()

    if not events:
        return {"events": [], "rows": []}

    event_ids = [e.id for e in events]
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    attendances = (
        db.query(Attendance)
        .options(joinedload(Attendance.player))
        .filter(Attendance.event_id.in_(event_ids))
        .all()
    )

    # Build player → {event_id: status}
    player_map: dict[int, dict] = {}
    for att in attendances:
        if att.player is None:
            continue
        if att.player_id not in player_map:
            player_map[att.player_id] = {"player": att.player, "statuses": {}}
        player_map[att.player_id]["statuses"][att.event_id] = att.status

    rows = []
    for entry in sorted(player_map.values(), key=lambda x: (x["player"].last_name or "", x["player"].first_name or "")):
        statuses = entry["statuses"]
        present = sum(1 for s in statuses.values() if s == "present")
        rows.append({
            "player": entry["player"],
            "statuses": statuses,
            "present_count": present,
            "total": len(event_ids),
        })

    return {"events": events, "rows": rows}


def get_player_attendance_history(db: Session, player_id: int, season_id: int | None = None) -> list[dict]:
    """Return list of {event, attendance} dicts sorted by event_date desc."""
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    q = db.query(Attendance).options(joinedload(Attendance.event)).filter(Attendance.player_id == player_id)
    if season_id is not None:
        q = q.join(Event, Attendance.event_id == Event.id).filter(Event.season_id == season_id)
    attendances = q.all()
    results = []
    for att in attendances:
        if att.event:
            results.append({"event": att.event, "attendance": att})
    results.sort(key=lambda x: x["event"].event_date, reverse=True)
    return results


def get_player_season_matrix(db: Session, player_id: int, season_id: int) -> dict:
    """Single-player matrix for one season: events grouped by month with status per event.

    Returns:
        {
            "months": [
                {
                    "label": "April 2026",
                    "events": [{"event": Event, "status": str}, ...]
                }, ...
            ],
            "present_count": int,
            "absent_count": int,
            "maybe_count": int,
            "unknown_count": int,
            "total": int,
        }
    """
    from collections import defaultdict  # noqa: PLC0415
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    events = db.query(Event).filter(Event.season_id == season_id).order_by(Event.event_date.asc()).all()
    if not events:
        return {"months": [], "present_count": 0, "absent_count": 0, "maybe_count": 0, "unknown_count": 0, "total": 0}

    event_ids = [e.id for e in events]
    attendances = (
        db.query(Attendance)
        .filter(Attendance.player_id == player_id, Attendance.event_id.in_(event_ids))
        .all()
    )
    status_map = {att.event_id: att.status for att in attendances}

    counts: dict[str, int] = {"present": 0, "absent": 0, "maybe": 0, "unknown": 0}
    months: dict[str, list] = defaultdict(list)
    for event in events:
        status = status_map.get(event.id, "unknown")
        counts[status if status in counts else "unknown"] += 1
        month_key = event.event_date.strftime("%Y-%m")
        months[month_key].append({"event": event, "status": status})

    return {
        "months": [{"key": k, "events": v} for k, v in sorted(months.items())],
        "present_count": counts["present"],
        "absent_count": counts["absent"],
        "maybe_count": counts["maybe"],
        "unknown_count": counts["unknown"],
        "total": len(events),
    }


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def _default_status(event: Event) -> str:
    """Return the automatic attendance status for a newly created record.

    * "all"  → everyone is present by default
    * anything else → unknown (player must respond)
    """
    return "present" if event.presence_type == "all" else "unknown"


def _has_higher_prio_conflict(db: Session, player: Player, event: Event) -> bool:
    """True if player has a higher-priority team with a conflicting event on the same date/time.

    Both PlayerTeam queries are scoped to event.season_id.
    If event.season_id is None, returns False (no conflict assumed).
    """
    if event.team_id is None:
        return False
    if event.season_id is None:
        return False

    # Query 1: player's own membership in this team for this season
    my_pt = (
        db.query(PlayerTeam).filter_by(player_id=player.id, team_id=event.team_id, season_id=event.season_id).first()
    )
    if my_pt is None:
        return False

    # Query 2: find all higher-priority teams for the player in this season
    higher_team_ids = [
        pt.team_id
        for pt in db.query(PlayerTeam)
        .filter(
            PlayerTeam.player_id == player.id,
            PlayerTeam.season_id == event.season_id,
            PlayerTeam.priority < my_pt.priority,
        )
        .all()
    ]
    if not higher_team_ids:
        return False

    competing = (
        db.query(Event)
        .filter(
            Event.event_date == event.event_date,
            Event.team_id.in_(higher_team_ids),
            Event.id != event.id,
        )
        .all()
    )
    for ce in competing:
        if event.event_time is None or ce.event_time is None:
            return True
        if event.event_time == ce.event_time:
            return True
    return False


def ensure_attendance_records(db: Session, event: Event) -> None:
    """Create Attendance rows for every active player in event's (team, season).

    If event.season_id is None, no records are created (season context required).
    Automatically applies any active absences to newly created records.
    """
    if event.team_id is None:
        return
    if event.season_id is None:
        import logging

        logging.getLogger(__name__).warning(
            "ensure_attendance_records called with event.season_id=None (event_id=%s). No attendance records created.",
            event.id,
        )
        return

    # Fetch players via (team_id, season_id) — season-scoped
    memberships = (
        db.query(PlayerTeam)
        .filter(
            PlayerTeam.team_id == event.team_id,
            PlayerTeam.season_id == event.season_id,
        )
        .all()
    )
    players = [m.player for m in memberships if m.player is not None and m.player.is_active and m.player.archived_at is None]

    existing_player_ids = {att.player_id for att in db.query(Attendance).filter(Attendance.event_id == event.id).all()}

    default = _default_status(event)
    new_records = []
    new_player_ids = []
    for player in players:
        if player.id not in existing_player_ids:
            status = default
            mem = next((m for m in memberships if m.player_id == player.id), None)
            if status != "absent" and mem is not None and mem.absent_by_default:
                status = "absent"
            if status != "absent" and _has_higher_prio_conflict(db, player, event):
                status = "absent"
            new_records.append(Attendance(event_id=event.id, player_id=player.id, status=status))
            new_player_ids.append(player.id)

    if new_records:
        db.add_all(new_records)
        db.commit()

        # Apply active absences to newly created records
        from services.absence_service import apply_absence_to_future_events, is_date_in_absence
        for player_id in new_player_ids:
            if is_date_in_absence(player_id, event.event_date, db):
                # Re-apply absences for this specific player (handles override logic)
                apply_absence_to_future_events(player_id, db)


def backfill_attendance_for_player(
    db: Session,
    player_id: int,
    team_id: int,
    season_id: int,
) -> int:
    """Create missing Attendance rows for an existing player newly added to a team.

    Called after a PlayerTeam row is inserted so the player appears on all
    existing events for that (team, season).

    Rules:
    - Past events (event_date < today): always set to "absent" so the coach
      can review and correct manually. Past records are never auto-set to
      "present" regardless of presence_type.
    - Future events: use _default_status(event) — "present" for all-attendee
      events, "unknown" otherwise. Respects absent_by_default and priority
      conflicts.
    - Never overwrites an existing Attendance row.

    Returns the number of new records created.
    """
    today = date.today()

    events = db.query(Event).filter(Event.team_id == team_id, Event.season_id == season_id).all()
    if not events:
        return 0

    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None or not player.is_active or player.archived_at is not None:
        return 0

    mem = db.query(PlayerTeam).filter_by(player_id=player_id, team_id=team_id, season_id=season_id).first()

    event_ids = [e.id for e in events]
    existing_event_ids = {
        att.event_id
        for att in db.query(Attendance.event_id)
        .filter(Attendance.event_id.in_(event_ids), Attendance.player_id == player_id)
        .all()
    }

    new_records = []
    for event in events:
        if event.id in existing_event_ids:
            continue

        if event.event_date < today:
            # Past event — always absent, no auto-present regardless of presence_type
            status = "absent"
        else:
            status = _default_status(event)
            if status != "absent" and mem is not None and mem.absent_by_default:
                status = "absent"
            if status != "absent" and _has_higher_prio_conflict(db, player, event):
                status = "absent"

        new_records.append(Attendance(event_id=event.id, player_id=player_id, status=status))

    if new_records:
        db.add_all(new_records)
        db.commit()

    return len(new_records)


def sync_attendance_defaults(db: Session, event: Event) -> None:
    """Promote still-unset (unknown) records to 'present' when the event is
    switched to presence_type='all'.

    Rules:
    - Only 'unknown' records are ever touched automatically.
    - 'absent', 'maybe', and manually-set 'present' are NEVER changed.
    - Switching *away* from 'all' does nothing automatically — players keep
      whatever status they already have.
    """
    if _default_status(event) != "present":
        # Not an "all-attendee" event: nothing to auto-promote.
        return

    records = (
        db.query(Attendance)
        .filter(
            Attendance.event_id == event.id,
            Attendance.status == "unknown",  # only touch truly unset records
        )
        .all()
    )
    for rec in records:
        rec.status = "present"
    if records:
        db.commit()
