"""routes/users.py — Admin user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.templates import render
from models.player import Player
from models.user import User
from routes._auth_helpers import NotAuthorized, require_admin

router = APIRouter()


@router.get("", dependencies=[Depends(require_admin)])
async def users_list(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    # Build player lookup: user_id -> Player
    players = db.query(Player).filter(Player.user_id.isnot(None)).all()
    player_by_user: dict[int, Player] = {p.user_id: p for p in players}
    return render(
        request,
        "auth/users_list.html",
        {
            "user": request.state.user,
            "users": users,
            "player_by_user": player_by_user,
        },
    )


@router.post("/{user_id}/toggle-active", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def toggle_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = request.state.user
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    # Cannot act on yourself
    if target.id == current_user.id:
        raise NotAuthorized

    # Cannot deactivate the last active admin
    if target.role == "admin" and target.is_active:
        active_admin_count = db.query(User).filter(
            User.role == "admin", User.is_active == True  # noqa: E712
        ).count()
        if active_admin_count <= 1:
            raise NotAuthorized

    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/delete", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = request.state.user
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    # Cannot delete yourself
    if target.id == current_user.id:
        raise NotAuthorized

    # Cannot delete the last active admin
    if target.role == "admin":
        active_admin_count = db.query(User).filter(
            User.role == "admin", User.is_active == True  # noqa: E712
        ).count()
        if active_admin_count <= 1:
            raise NotAuthorized

    db.delete(target)
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)
