"""routes/attendance.py — Attendance marking page and status updates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from routes._auth_helpers import require_login
from services.attendance_service import get_event_attendance_summary, set_attendance

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Attendance marking page
# ---------------------------------------------------------------------------


@router.get("/{event_id}")
async def attendance_page(event_id: int, request: Request, db: Session = Depends(get_db)):
    result = require_login(request)
    if isinstance(result, Response):
        return result

    user = result
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    if user.is_admin:
        # Admins see all players
        attendances = (
            db.query(Attendance).filter(Attendance.event_id == event_id).all()
        )
        my_players: list[Player] = []
        summary = get_event_attendance_summary(db, event_id)
    else:
        # Members see only their own linked player(s)
        my_players = (
            db.query(Player).filter(Player.user_id == user.id).all()
        )
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

    # Build map player_id -> attendance for easy template lookup
    att_map = {att.player_id: att for att in attendances}

    return templates.TemplateResponse(request, "attendance/mark.html", {"user": user,
            "event": event,
            "attendances": attendances,
            "att_map": att_map,
            "my_players": my_players,
            "summary": summary,
            "flash": request.query_params.get("flash")})


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
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    result = require_login(request)
    if isinstance(result, Response):
        return result

    user = result

    # Members may only update their own players
    if not user.is_admin:
        player = db.get(Player, player_id)
        if player is None or player.user_id != user.id:
            return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    valid_statuses = {"present", "absent", "maybe", "unknown"}
    if status not in valid_statuses:
        return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    set_attendance(db, event_id, player_id, status, note)
    return RedirectResponse(f"/attendance/{event_id}?flash=Saved", status_code=302)
