"""routes/users.py — Admin user management."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.session import COOKIE_NAME
from app.templates import render
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import NotAuthorized, require_admin, rt
from services import email_service
from services.auth_service import create_magic_link, create_session_cookie, hash_password
from services.email_service import send_reset_email, send_welcome_email

router = APIRouter()


@router.get("/register", dependencies=[Depends(require_admin)])
async def register_get(request: Request):
    from models.user import User as _User  # noqa: F401
    return render(request, "auth/register.html", {"user": request.state.user, "error": None, "flash": None})


@router.post("/register", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def register_post(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("member"),
    phone: str = Form(""),
    locale: str = Form("en"),
    first_name: str = Form(""),
    last_name: str = Form(""),
):
    from services.auth_service import create_user, get_user_by_email, get_user_by_username

    username = username.strip()
    email = email.strip()

    def error(msg: str):
        return render(
            request,
            "auth/register.html",
            {"user": request.state.user, "error": msg, "flash": None},
            status_code=400,
        )

    if role not in {"admin", "coach", "member"}:
        return error(rt(request, "errors.invalid_role"))
    if get_user_by_username(db, username):
        return error(rt(request, "errors.username_taken", username=username))
    if get_user_by_email(db, email):
        return error(rt(request, "errors.email_taken", email=email))
    if len(password) < 8:
        return error(rt(request, "errors.password_too_short"))

    new_user = create_user(
        db,
        username=username,
        email=email,
        password=password,
        role=role,
        phone=phone or None,
        locale=locale or None,
        first_name=first_name or None,
        last_name=last_name or None,
    )
    magic = create_magic_link(new_user.id, "/dashboard")
    send_welcome_email(
        to=new_user.email,
        username=new_user.username,
        password=password,
        locale=new_user.locale or "en",
        magic_link=magic,
    )
    return render(
        request,
        "auth/register.html",
        {
            "user": request.state.user,
            "error": None,
            "flash": f"User '{username}' created successfully.",
        },
    )


@router.get("", dependencies=[Depends(require_admin)])
async def users_list(request: Request, db: Session = Depends(get_db), reset: str | None = None):
    users = db.query(User).order_by(User.created_at.desc()).all()
    # Build player lookup: user_id -> Player
    linked_players = db.query(Player).filter(Player.user_id.isnot(None)).all()
    player_by_user: dict[int, Player] = {p.user_id: p for p in linked_players}
    return render(
        request,
        "auth/users_list.html",
        {
            "user": request.state.user,
            "users": users,
            "player_by_user": player_by_user,
            "password_reset": reset == "1",
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
    q = db.query(Player).filter(
        Player.is_active == True,  # noqa: E712
        Player.email.isnot(None),
        Player.email != "",
        Player.user_id.is_(None),
        Player.archived_at.is_(None),
    )

    # Apply team/season filter via PlayerTeam join
    if selected_team_id:
        pt_q = db.query(PlayerTeam.player_id).filter(PlayerTeam.team_id == selected_team_id)
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
        Player.archived_at.is_(None),
    )
    if selected_team_id:
        no_email_q = no_email_q.filter(
            Player.id.in_(
                [row[0] for row in db.query(PlayerTeam.player_id).filter(PlayerTeam.team_id == selected_team_id).all()]
            )
        )
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
    locale: str = Form(default="en"),
):
    if role not in ("admin", "coach", "member"):
        role = "member"
    if locale not in ("en", "it", "fr", "de"):
        locale = "en"

    created = 0
    skipped = 0
    email_failed: list[str] = []

    for pid in player_ids:
        player = db.get(Player, pid)
        if player is None:
            skipped += 1
            continue
        if player.archived_at is not None:
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
        existing = db.query(User).filter((User.username == player.email) | (User.email == player.email)).first()
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
            locale=locale,
            must_change_password=True,
        )
        db.add(new_user)
        db.flush()  # get new_user.id
        player.user_id = new_user.id

        magic = create_magic_link(new_user.id, "/dashboard")
        sent = send_welcome_email(
            to=player.email,
            username=player.email,
            password=pw,
            locale=locale,
            magic_link=magic,
        )
        if sent:
            created += 1
        else:
            email_failed.append(player.full_name)
            created += 1  # account created even if email failed

    db.commit()

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


@router.get("/{user_id}/edit", dependencies=[Depends(require_admin)])
async def user_edit_get(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    player_team_id: str | None = None,
    player_season_id: str | None = None,
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)
    linked_player = db.query(Player).filter(Player.user_id == user_id).first()

    teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    p_team_id = int(player_team_id) if player_team_id and player_team_id.strip() else None
    p_season_id = int(player_season_id) if player_season_id and player_season_id.strip() else None

    q = db.query(Player).filter(Player.user_id.is_(None), Player.archived_at.is_(None))
    if p_team_id:
        from models.player_team import PlayerTeam
        player_ids = [r[0] for r in db.query(PlayerTeam.player_id).filter(PlayerTeam.team_id == p_team_id).all()]
        q = q.filter(Player.id.in_(player_ids))
    if p_season_id:
        from models.player_team import PlayerTeam
        player_ids = [r[0] for r in db.query(PlayerTeam.player_id).filter(PlayerTeam.season_id == p_season_id).all()]
        q = q.filter(Player.id.in_(player_ids))
    unlinked_players = q.order_by(Player.last_name, Player.first_name).all()

    return render(request, "auth/user_form.html", {
        "user": request.state.user,
        "target": target,
        "is_admin_edit": True,
        "error": None,
        "linked_player": linked_player,
        "unlinked_players": unlinked_players,
        "teams": teams,
        "seasons": seasons,
        "selected_team_id": p_team_id,
        "selected_season_id": p_season_id,
    })


@router.post("/{user_id}/edit", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def user_edit_post(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    locale: str = Form("en"),
    phone: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    new_password: str = Form(""),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    username = username.strip()
    email = email.strip()

    def _edit_error(msg: str, code: int = 400):
        linked_player = db.query(Player).filter(Player.user_id == user_id).first()
        return render(request, "auth/user_form.html", {
            "user": request.state.user, "target": target, "is_admin_edit": True, "error": msg,
            "linked_player": linked_player,
            "unlinked_players": db.query(Player).filter(Player.user_id.is_(None), Player.archived_at.is_(None)).order_by(Player.last_name, Player.first_name).all(),
            "teams": db.query(Team).order_by(Team.name).all(),
            "seasons": db.query(Season).order_by(Season.name).all(),
            "selected_team_id": None, "selected_season_id": None,
        }, status_code=code)

    if not username:
        return _edit_error(rt(request, "errors.field_required", field="Username"))
    if not email:
        return _edit_error(rt(request, "errors.field_required", field="Email"))
    if role not in ("admin", "coach", "member"):
        role = "member"
    if new_password and len(new_password) < 8:
        return _edit_error(rt(request, "errors.password_too_short"))

    dup_user = db.query(User).filter(User.username == username, User.id != user_id).first()
    if dup_user:
        return _edit_error(rt(request, "errors.username_taken", username=username))
    dup_email = db.query(User).filter(User.email == email, User.id != user_id).first()
    if dup_email:
        return _edit_error(rt(request, "errors.email_taken", email=email))

    target.username = username
    target.email = email
    target.role = role
    target.locale = locale
    target.phone = phone.strip() or None
    target.first_name = first_name.strip() or None
    target.last_name = last_name.strip() or None
    if new_password:
        target.hashed_password = hash_password(new_password)
    # Sync name to linked player if present
    for player in target.players:
        if target.first_name:
            player.first_name = target.first_name
        if target.last_name:
            player.last_name = target.last_name
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/link-player", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def link_player(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    player_id: int = Form(...),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    player = db.get(Player, player_id)
    if player is None or player.user_id is not None:
        return RedirectResponse("/auth/users", status_code=302)

    # Unlink any existing player linked to this user first
    existing = db.query(Player).filter(Player.user_id == user_id).first()
    if existing:
        existing.user_id = None

    player.user_id = user_id
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/unlink-player", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def unlink_player(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    player = db.query(Player).filter(Player.user_id == user_id).first()
    if player:
        player.user_id = None
        db.commit()
    return RedirectResponse("/auth/users", status_code=302)


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
        active_admin_count = (
            db.query(User)
            .filter(
                User.role == "admin",
                User.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active_admin_count <= 1:
            raise NotAuthorized

    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/reset-password", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def reset_password(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    new_pw = secrets.token_urlsafe(12)
    target.hashed_password = hash_password(new_pw)
    target.must_change_password = True
    db.commit()

    magic = create_magic_link(target.id, "/dashboard")
    send_reset_email(
        to=target.email,
        username=target.username,
        password=new_pw,
        locale=target.locale or "en",
        magic_link=magic,
    )

    return RedirectResponse("/auth/users?reset=1", status_code=302)


@router.post("/{user_id}/send-welcome", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def send_welcome(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    new_pw = secrets.token_urlsafe(12)
    target.hashed_password = hash_password(new_pw)
    target.must_change_password = True
    db.commit()

    magic = create_magic_link(target.id, "/dashboard")
    send_welcome_email(
        to=target.email,
        username=target.username,
        password=new_pw,
        locale=target.locale or "en",
        magic_link=magic,
    )

    return RedirectResponse("/auth/users?welcome=1", status_code=302)


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
        active_admin_count = (
            db.query(User)
            .filter(
                User.role == "admin",
                User.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active_admin_count <= 1:
            raise NotAuthorized

    db.delete(target)
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/impersonate", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def impersonate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = request.state.user
    if current_user.id == user_id:
        return RedirectResponse("/auth/users", status_code=302)
    target = db.get(User, user_id)
    if target is None or not target.is_active:
        raise NotAuthorized

    orig_session = request.cookies.get(COOKIE_NAME, "")
    new_session = create_session_cookie(target.id)

    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(COOKIE_NAME, new_session, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE, max_age=60 * 60 * 24 * 7)
    response.set_cookie("_orig_session", orig_session, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE, max_age=60 * 60 * 8)
    return response
