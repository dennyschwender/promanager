"""routes/attendance.py — Attendance marking page and status updates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.player_team import PlayerTeam
from models.user import User
from routes._auth_helpers import require_coach_or_admin, require_login, rt
from services.attendance_service import set_attendance

router = APIRouter()


# ---------------------------------------------------------------------------
# Borrow a player for a single event
# ---------------------------------------------------------------------------


@router.post("/{event_id}/borrow")
async def borrow_player(
    event_id: int,
    request: Request,
    player_id: int = Form(...),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    """Add a player from another team to this event's attendance."""
    event = db.get(Event, event_id)
    if event is None:
        return JSONResponse({"ok": False, "error": "event_not_found"}, status_code=404)

    player = db.get(Player, player_id)
    if player is None or not player.is_active:
        return JSONResponse({"ok": False, "error": "player_not_found"}, status_code=404)

    existing = db.query(Attendance).filter(Attendance.event_id == event_id, Attendance.player_id == player_id).first()
    if existing:
        return JSONResponse({"ok": False, "error": "already_attending"}, status_code=409)

    # Resolve player's home team for this event's season
    borrowed_from_team_id: int | None = None
    team_name: str | None = None
    if event.season_id is not None:
        mem = (
            db.query(PlayerTeam)
            .filter(PlayerTeam.player_id == player_id, PlayerTeam.season_id == event.season_id)
            .order_by(PlayerTeam.priority.asc())
            .first()
        )
        if mem is not None:
            from models.team import Team  # noqa: PLC0415

            team = db.get(Team, mem.team_id)
            if team:
                borrowed_from_team_id = team.id
                team_name = team.name

    att = Attendance(
        event_id=event_id,
        player_id=player_id,
        status="unknown",
        borrowed_from_team_id=borrowed_from_team_id,
    )
    db.add(att)
    db.commit()

    return JSONResponse(
        {
            "ok": True,
            "player_id": player_id,
            "full_name": f"{player.first_name} {player.last_name}",
            "team_name": team_name,
        }
    )


# ---------------------------------------------------------------------------
# Update attendance for one player
# ---------------------------------------------------------------------------


@router.post("/{event_id}/{player_id}")
async def update_attendance(
    event_id: int,
    player_id: int,
    request: Request,
    status: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    # Detect AJAX caller — must happen first so all error paths can branch
    wants_json = "application/json" in request.headers.get("accept", "")

    # Validate status early so JSON callers get a proper error
    valid_statuses = {"present", "absent", "maybe", "unknown"}
    if status not in valid_statuses:
        if wants_json:
            return JSONResponse({"ok": False, "error": "invalid_status"}, status_code=400)
        return RedirectResponse(f"/events/{event_id}", status_code=302)

    # Authorization check
    if user.is_admin:
        pass  # full access
    elif user.is_coach:
        event = db.get(Event, event_id)
        if event is None:
            if wants_json:
                return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
            return RedirectResponse(f"/events/{event_id}", status_code=302)
        from routes._auth_helpers import check_team_access  # noqa: PLC0415

        check_team_access(user, event.team_id, db, season_id=event.season_id)
    else:
        player = db.get(Player, player_id)
        if player is None or player.user_id != user.id:
            if wants_json:
                return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=403)
            return RedirectResponse(f"/events/{event_id}", status_code=302)

    set_attendance(db, event_id, player_id, status, note)

    if wants_json:
        return JSONResponse({"ok": True, "status": status, "note": note})

    from urllib.parse import quote  # noqa: PLC0415

    flash_msg = quote(rt(request, "common.changes_saved"))
    return RedirectResponse(f"/events/{event_id}?flash={flash_msg}", status_code=302)
