"""routes/users.py — Admin user management."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.templates import render
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import NotAuthorized, require_admin
from services import email_service
from services.auth_service import hash_password

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


@router.get("/bulk-create", dependencies=[Depends(require_admin)])
async def bulk_create_get(
    request: Request,
    team_id: str | None = None,
    season_id: str | None = None,
    db: Session = Depends(get_db),
):
    selected_team_id = int(team_id) if team_id and team_id.strip() else None
    selected_season_id = int(season_id) if season_id and season_id.strip() else None

    teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    # Find existing user emails/usernames to exclude
    existing_emails = {row[0] for row in db.query(User.email).all()}
    existing_usernames = {row[0] for row in db.query(User.username).all()}
    taken = existing_emails | existing_usernames

    # Base query: active players with email, no user_id
    q = (
        db.query(Player)
        .filter(
            Player.is_active == True,  # noqa: E712
            Player.email.isnot(None),
            Player.email != "",
            Player.user_id.is_(None),
        )
    )

    # Apply team/season filter via PlayerTeam join
    if selected_team_id:
        pt_q = db.query(PlayerTeam.player_id).filter(
            PlayerTeam.team_id == selected_team_id
        )
        if selected_season_id:
            pt_q = pt_q.filter(PlayerTeam.season_id == selected_season_id)
        player_ids_in_team = [row[0] for row in pt_q.all()]
        q = q.filter(Player.id.in_(player_ids_in_team))

    all_eligible_with_email = q.all()
    eligible = [p for p in all_eligible_with_email if p.email not in taken]

    # Count players without email (for note)
    no_email_q = db.query(Player).filter(
        Player.is_active == True,  # noqa: E712
        (Player.email.is_(None)) | (Player.email == ""),
        Player.user_id.is_(None),
    )
    if selected_team_id:
        no_email_q = no_email_q.filter(Player.id.in_(
            [row[0] for row in db.query(PlayerTeam.player_id)
             .filter(PlayerTeam.team_id == selected_team_id).all()]
        ))
    no_email_count = no_email_q.count()

    return render(
        request,
        "auth/bulk_create_users.html",
        {
            "user": request.state.user,
            "teams": teams,
            "seasons": seasons,
            "selected_team_id": selected_team_id,
            "selected_season_id": selected_season_id,
            "eligible": eligible,
            "no_email_count": no_email_count,
            "results": None,
        },
    )


@router.post("/bulk-create", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def bulk_create_post(
    request: Request,
    db: Session = Depends(get_db),
    player_ids: list[int] = Form(default=[]),
    role: str = Form(default="member"),
):
    if role not in ("admin", "coach", "member"):
        role = "member"

    created = 0
    skipped = 0
    email_failed: list[str] = []

    for pid in player_ids:
        player = db.get(Player, pid)
        if player is None:
            skipped += 1
            continue
        # Skip if already linked
        if player.user_id is not None:
            skipped += 1
            continue
        # Skip if no email
        if not player.email:
            skipped += 1
            continue
        # Skip if email already used as username or email on another User
        existing = db.query(User).filter(
            (User.username == player.email) | (User.email == player.email)
        ).first()
        if existing:
            skipped += 1
            continue

        # Create user
        pw = secrets.token_urlsafe(12)
        new_user = User(
            username=player.email,
            email=player.email,
            hashed_password=hash_password(pw),
            role=role,
        )
        db.add(new_user)
        db.flush()  # get new_user.id
        player.user_id = new_user.id
        db.commit()

        # Send welcome email
        sent = email_service.send_email(
            to=player.email,
            subject="Your ProManager account",
            body_html=f"<p>Your account has been created.<br>Username: <strong>{player.email}</strong><br>Password: <strong>{pw}</strong></p>",
            body_text=f"Your account has been created.\nUsername: {player.email}\nPassword: {pw}",
        )
        if sent:
            created += 1
        else:
            email_failed.append(player.full_name)
            created += 1  # account created even if email failed

    teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    return render(
        request,
        "auth/bulk_create_users.html",
        {
            "user": request.state.user,
            "teams": teams,
            "seasons": seasons,
            "selected_team_id": None,
            "selected_season_id": None,
            "eligible": [],
            "no_email_count": 0,
            "already_taken_count": 0,
            "results": {
                "created": created,
                "skipped": skipped,
                "email_failed": email_failed,
            },
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
