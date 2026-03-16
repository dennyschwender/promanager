"""services/attendance_service.py — Attendance business logic."""

from __future__ import annotations

from datetime import datetime, timezone

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
    note: str = "",
) -> Attendance:
    """Set (or create) the attendance record for a player/event pair."""
    att = get_or_create_attendance(db, event_id, player_id)
    att.status = status
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
    attendances = db.query(Attendance).filter(Attendance.event_id == event_id).all()
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


def get_season_attendance_stats(db: Session, season_id: int) -> list[dict]:
    """Per-player stats for an entire season.

    Returns a list of dicts:
        {player, present_count, absent_count, maybe_count, unknown_count, total_events}
    """
    # Find all events for this season
    events = db.query(Event).filter(Event.season_id == season_id).all()
    event_ids = [e.id for e in events]
    total_events = len(event_ids)

    if not event_ids:
        return []

    # Collect all attendances for those events
    attendances = db.query(Attendance).filter(Attendance.event_id.in_(event_ids)).all()

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


def get_player_attendance_history(db: Session, player_id: int) -> list[dict]:
    """Return list of {event, attendance} dicts sorted by event_date desc."""
    attendances = db.query(Attendance).filter(Attendance.player_id == player_id).all()
    results = []
    for att in attendances:
        if att.event:
            results.append({"event": att.event, "attendance": att})
    results.sort(key=lambda x: x["event"].event_date, reverse=True)
    return results


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
    players = [m.player for m in memberships if m.player is not None and m.player.is_active]

    existing_player_ids = {att.player_id for att in db.query(Attendance).filter(Attendance.event_id == event.id).all()}

    default = _default_status(event)
    new_records = []
    for player in players:
        if player.id not in existing_player_ids:
            status = default
            mem = next((m for m in memberships if m.player_id == player.id), None)
            if status != "absent" and mem is not None and mem.absent_by_default:
                status = "absent"
            if status != "absent" and _has_higher_prio_conflict(db, player, event):
                status = "absent"
            new_records.append(Attendance(event_id=event.id, player_id=player.id, status=status))

    if new_records:
        db.add_all(new_records)
        db.commit()


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
