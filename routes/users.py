"""routes/users.py — Admin user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.player import Player
from models.user import User
from routes._auth_helpers import require_admin

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
