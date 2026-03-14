"""routes/auth.py — Login, logout, and admin user registration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.limiter import limiter
from app.templates import render
from models.user import User
from routes._auth_helpers import require_admin
from services.auth_service import (
    authenticate_user,
    create_session_cookie,
    create_user,
    get_user_by_email,
    get_user_by_username,
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
        return render(request, "auth/login.html", {"user": None,
                "error": "Invalid username or password."},
            status_code=401)

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
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    # Validation
    if get_user_by_username(db, username):
        return render(request, "auth/register.html", {
            "user": user,
            "error": f"Username '{username}' is already taken.",
            "flash": None,
        }, status_code=400)
    if get_user_by_email(db, email):
        return render(request, "auth/register.html", {
            "user": user,
            "error": f"Email '{email}' is already registered.",
            "flash": None,
        }, status_code=400)
    if len(password) < 8:
        return render(request, "auth/register.html", {
            "user": user,
            "error": "Password must be at least 8 characters.",
            "flash": None,
        }, status_code=400)

    create_user(db, username=username, email=email, password=password, role=role)
    return render(request, "auth/register.html", {
        "user": user,
        "error": None,
        "flash": f"User '{username}' created successfully.",
    })
