"""routes/auth.py — Login, logout, and admin user registration."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import quote

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
from routes._auth_helpers import require_admin, require_login, rt
from services.audit_service import log_action
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
        log_action("auth.login_failed", actor_username=username, extra={"username": username}, request=request)
        return render(
            request,
            "auth/login.html",
            {"user": None, "error": rt(request, "errors.invalid_credentials")},
            status_code=401,
        )

    log_action("auth.login", actor_user_id=user.id, actor_username=user.username, request=request)
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
async def logout(request: Request):
    if request.state.user:
        log_action("auth.logout", request=request)
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
    send_welcome_email: str = Form(""),
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

    if send_welcome_email == "1" and email:
        from services.email_service import send_welcome_email as _send_welcome  # noqa: PLC0415
        _send_welcome(to=email, username=username, password=password, locale=locale or "en")

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
@limiter.limit("30/minute")
async def magic_link_login(
    request: Request,
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
    saved = "saved" in request.query_params
    return render(request, "auth/change_password.html", {"user": user, "error": None, "saved": saved})


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

    log_action("auth.change_password", request=request)
    return RedirectResponse("/auth/change-password?saved=1", status_code=302)


# ---------------------------------------------------------------------------
# Stop impersonating (restore admin session)
# ---------------------------------------------------------------------------


@router.get("/stop-impersonating")
async def stop_impersonating(request: Request):
    orig_session = request.cookies.get("_orig_session", "")
    log_action("auth.stop_impersonate", request=request)
    response = RedirectResponse("/auth/users", status_code=302)
    if orig_session:
        from itsdangerous import BadSignature, SignatureExpired  # noqa: PLC0415

        from app.session import _signer  # noqa: PLC0415
        try:
            user_id_bytes = _signer.unsign(orig_session, max_age=60 * 60 * 24 * 7)
            restored_cookie = create_session_cookie(int(user_id_bytes))
            response.set_cookie(
                COOKIE_NAME,
                restored_cookie,
                httponly=True,
                samesite="lax",
                secure=settings.COOKIE_SECURE,
                max_age=60 * 60 * 24 * 7,
            )
        except (BadSignature, SignatureExpired, ValueError):
            pass  # Invalid token — don't restore; user lands on /auth/users unauthenticated
    response.delete_cookie("_orig_session")
    return response


# ---------------------------------------------------------------------------
# Log out all devices (session invalidation)
# ---------------------------------------------------------------------------


@router.post("/logout-all")
async def logout_all_post(
    request: Request,
    _csrf: None = Depends(require_csrf),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    db_user.logout_all_at = datetime.now(timezone.utc)
    db.commit()

    log_action("auth.logout_all", request=request)
    # Re-issue a fresh session cookie so the current session stays valid
    new_cookie = create_session_cookie(user.id)
    flash_msg = quote(rt(request, "auth.logout_all_done"))
    response = RedirectResponse(f"/profile?flash={flash_msg}", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        new_cookie,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,
    )
    return response


# ---------------------------------------------------------------------------
# Forgot password (self-service)
# ---------------------------------------------------------------------------


@router.get("/forgot-password")
@limiter.limit("10/minute")
async def forgot_password_get(request: Request):
    if request.state.user:
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "auth/forgot_password.html", {"user": None, "sent": False, "error": None})


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from services.email_service import send_forgot_password_email  # noqa: PLC0415

    user = get_user_by_email(db, email.strip().lower())
    if user and user.is_active:
        new_password = secrets.token_urlsafe(10)
        user.hashed_password = hash_password(new_password)
        user.must_change_password = True
        db.commit()
        send_forgot_password_email(
            to=user.email,
            username=user.username,
            password=new_password,
            locale=getattr(user, "locale", "en") or "en",
        )

    if user and user.is_active:
        log_action("auth.forgot_password", target_type="user", target_id=user.id,
                   target_label=user.username, request=request)
    # Always show success to avoid user enumeration
    return render(request, "auth/forgot_password.html", {"user": None, "sent": True, "error": None})
