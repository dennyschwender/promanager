"""routes/attendance.py — Attendance marking page and status updates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.templates import render
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.user import User
from routes._auth_helpers import require_login, rt
from services.attendance_service import get_event_attendance_summary, set_attendance

router = APIRouter()


# ---------------------------------------------------------------------------
# Attendance marking page
# ---------------------------------------------------------------------------


@router.get("/{event_id}")
async def attendance_page(
    event_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    if user.is_admin:
        attendances = db.query(Attendance).filter(Attendance.event_id == event_id).all()
        my_players: list[Player] = []
        summary = get_event_attendance_summary(db, event_id)
        is_admin_view = True
    elif user.is_coach:
        from routes._auth_helpers import check_team_access  # noqa: PLC0415

        check_team_access(user, event.team_id, db, season_id=event.season_id)
        attendances = db.query(Attendance).filter(Attendance.event_id == event_id).all()
        my_players = []
        summary = get_event_attendance_summary(db, event_id)
        is_admin_view = True
    else:
        my_players = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).all()
        player_ids = [p.id for p in my_players]
        attendances = (
            db.query(Attendance)
            .filter(
                Attendance.event_id == event_id,
                Attendance.player_id.in_(player_ids),
            )
            .all()
        )
        summary = None
        is_admin_view = False

    att_map = {att.player_id: att for att in attendances}

    return render(
        request,
        "attendance/mark.html",
        {
            "user": user,
            "event": event,
            "attendances": attendances,
            "att_map": att_map,
            "my_players": my_players,
            "summary": summary,
            "is_admin_view": is_admin_view,
            "flash": request.query_params.get("flash"),
        },
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
        return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    # Authorization check
    if user.is_admin:
        pass  # full access
    elif user.is_coach:
        event = db.get(Event, event_id)
        if event is None:
            if wants_json:
                return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
            return RedirectResponse(f"/attendance/{event_id}", status_code=302)
        from routes._auth_helpers import check_team_access  # noqa: PLC0415

        check_team_access(user, event.team_id, db, season_id=event.season_id)
    else:
        player = db.get(Player, player_id)
        if player is None or player.user_id != user.id:
            if wants_json:
                return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=403)
            return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    set_attendance(db, event_id, player_id, status, note)

    if wants_json:
        return JSONResponse({"ok": True, "status": status, "note": note})

    from urllib.parse import quote  # noqa: PLC0415

    flash_msg = quote(rt(request, "common.changes_saved"))
    return RedirectResponse(f"/attendance/{event_id}?flash={flash_msg}", status_code=302)
