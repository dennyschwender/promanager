"""routes/auth.py — Login, logout, and admin user registration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.limiter import limiter
from app.templates import render
from models.user import User
from routes._auth_helpers import require_admin, rt
from services.auth_service import (
    authenticate_user,
    create_session_cookie,
    create_user,
    get_user_by_email,
    get_user_by_username,
    hash_password,
    verify_magic_link,
)

router = APIRouter()

COOKIE_NAME = "session_user_id"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.get("/login")
async def login_get(request: Request):
    if request.state.user:
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "auth/login.html", {"user": request.state.user, "error": None})


@router.post("/login")
@limiter.limit("10/minute")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if user is None:
        return render(
            request,
            "auth/login.html",
            {"user": None, "error": rt(request, "errors.invalid_credentials")},
            status_code=401,
        )

    cookie_val = create_session_cookie(user.id)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        cookie_val,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return response


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.get("/logout")
async def logout():
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Register (admin-only — creates new user accounts)
# ---------------------------------------------------------------------------


@router.get("/register")
async def register_get(
    request: Request,
    user: User = Depends(require_admin),
):
    return render(request, "auth/register.html", {"user": user, "error": None, "flash": None})


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("member"),
    phone: str = Form(""),
    locale: str = Form("en"),
    first_name: str = Form(""),
    last_name: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form_data = {"username": username, "email": email, "role": role, "phone": phone, "locale": locale, "first_name": first_name, "last_name": last_name}

    def error(msg: str):
        return render(
            request,
            "auth/register.html",
            {"user": user, "error": msg, "flash": None, "form_data": form_data},
            status_code=400,
        )

    # Validation
    if role not in {"admin", "coach", "member"}:
        return error(rt(request, "errors.invalid_role"))
    if get_user_by_username(db, username):
        return error(rt(request, "errors.username_taken", username=username))
    if get_user_by_email(db, email):
        return error(rt(request, "errors.email_taken", email=email))
    if len(password) < 8:
        return error(rt(request, "errors.password_too_short"))

    create_user(db, username=username, email=email, password=password, role=role, phone=phone or None, locale=locale or None, first_name=first_name or None, last_name=last_name or None)
    return render(
        request,
        "auth/register.html",
        {
            "user": user,
            "error": None,
            "flash": f"User '{username}' created successfully.",
        },
    )


# ---------------------------------------------------------------------------
# Magic login link
# ---------------------------------------------------------------------------


@router.get("/magic")
async def magic_link_login(
    token: str = "",
    db: Session = Depends(get_db),
):
    """Verify a magic link token, set session cookie, and redirect to the encoded path.

    On failure (invalid/expired/missing token), redirect to /auth/login.
    """
    if not token:
        return RedirectResponse("/auth/login", status_code=302)
    try:
        user_id, redirect_path = verify_magic_link(token)
    except (BadSignature, SignatureExpired, KeyError):
        return RedirectResponse("/auth/login?error=link_expired", status_code=302)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return RedirectResponse("/auth/login", status_code=302)

    cookie_val = create_session_cookie(user.id)
    response = RedirectResponse(redirect_path, status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        cookie_val,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return response


# ---------------------------------------------------------------------------
# Change password (forced on first login)
# ---------------------------------------------------------------------------


@router.get("/change-password")
async def change_password_get(
    request: Request,
    db: Session = Depends(get_db),
):
    user = request.state.user
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    return render(request, "auth/change_password.html", {"user": user, "error": None})


@router.post("/change-password")
async def change_password_post(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    user = request.state.user
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)

    def _error(msg: str):
        return render(request, "auth/change_password.html", {"user": user, "error": msg}, status_code=400)

    if len(new_password) < 8:
        return _error(rt(request, "errors.password_too_short"))
    if new_password != confirm_password:
        return _error(rt(request, "auth.change_password_mismatch"))

    db_user = db.get(User, user.id)
    db_user.hashed_password = hash_password(new_password)
    db_user.must_change_password = False
    db.commit()

    return RedirectResponse("/dashboard", status_code=302)
