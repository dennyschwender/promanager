"""app/main.py — FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings
from app.csrf import generate_csrf_token
from app.database import init_db
from app.limiter import limiter
from app.middleware.locale import LocaleMiddleware
from app.session import COOKIE_NAME
from app.session import get_user_from_cookie as _get_user_from_cookie
from app.templates import render
from routes._auth_helpers import NotAuthenticated, NotAuthorized

logger = logging.getLogger(__name__)

# Set by the lifespan on shutdown so long-lived generators (SSE) can exit cleanly.
shutdown_event = asyncio.Event()

# ---------------------------------------------------------------------------
# Middleware — inject request.state.user
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Reads the signed session cookie and attaches the User to request.state."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.user = _get_user_from_cookie(request)
        request.state.csrf_token = generate_csrf_token(request.cookies.get(COOKIE_NAME, ""))
        # Embed unread notification count for the bell badge
        request.state.unread_count = 0
        if request.state.user is not None:
            from app import database as _db_mod  # noqa: PLC0415
            from models.notification import Notification  # noqa: PLC0415
            from models.player import Player  # noqa: PLC0415

            db = _db_mod.SessionLocal()
            try:
                # Find player(s) linked to this user
                player_ids = [
                    pid
                    for (pid,) in db.query(Player.id)
                    .filter(
                        Player.user_id == request.state.user.id,
                        Player.is_active.is_(True),
                    )
                    .all()
                ]
                if player_ids:
                    request.state.unread_count = (
                        db.query(Notification)
                        .filter(
                            Notification.player_id.in_(player_ids),
                            Notification.is_read.is_(False),
                        )
                        .count()
                    )
            finally:
                db.close()
        # Force password change before any other page
        _CHANGE_PW_PATH = "/auth/change-password"
        _CHANGE_PW_ALLOWED = {_CHANGE_PW_PATH, "/auth/logout", "/auth/magic", "/auth/stop-impersonating", "/auth/logout-all", "/healthz"}
        if (
            request.state.user is not None
            and getattr(request.state.user, "must_change_password", False)
            and request.url.path not in _CHANGE_PW_ALLOWED
            and not request.url.path.startswith("/static")
        ):
            return RedirectResponse(_CHANGE_PW_PATH, status_code=302)

        response = await call_next(request)
        return response


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _weak_keys = {
        "change-me-in-production",
        "change-me-to-a-long-random-string-before-production",
    }
    if settings.SECRET_KEY in _weak_keys:
        logger.warning(
            "SECRET_KEY is set to the default insecure value. "
            'Generate a new one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    logger.info("Starting up — initialising database …")
    init_db()
    logger.info("Database ready.")

    # ── Telegram Bot ──────────────────────────────────────────────────────
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_WEBHOOK_URL and settings.TELEGRAM_WEBHOOK_SECRET:
        try:
            import bot as _bot  # noqa: PLC0415

            tg_app = await _bot.init_application(settings.TELEGRAM_BOT_TOKEN)
            webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL.rstrip('/')}/telegram/webhook"
            await tg_app.bot.set_webhook(
                url=webhook_url,
                secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            )
            logger.info("Telegram webhook registered at %s", webhook_url)
        except Exception:
            logger.exception("Failed to initialise Telegram bot — continuing without it.")
    else:
        logger.info(
            "Telegram bot not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_WEBHOOK_URL/TELEGRAM_WEBHOOK_SECRET not set)."
        )

    # ── Background scheduler ──────────────────────────────────────────────
    from services.scheduler import backup_loop, reminder_loop  # noqa: PLC0415

    _reminder_task = asyncio.create_task(reminder_loop())
    _backup_task = asyncio.create_task(backup_loop())

    yield

    logger.info("Shutting down.")
    shutdown_event.set()
    for _task in (_reminder_task, _backup_task):
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass

    # ── Telegram Bot shutdown ─────────────────────────────────────────────
    try:
        import bot as _bot  # noqa: PLC0415

        if _bot.telegram_app is not None:
            await _bot.telegram_app.bot.delete_webhook()
            await _bot.shutdown_application()
            logger.info("Telegram webhook deregistered.")
    except Exception:
        logger.debug("Telegram bot not active on shutdown.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Self-hosted player presence/absence tracker.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── Static files ──────────────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ── Rate limiting ─────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Middleware ────────────────────────────────────────────────────────
    app.add_middleware(LocaleMiddleware)  # added first → executes second (inner)
    app.add_middleware(AuthMiddleware)  # added second → executes first (outer)

    # ── Routers ───────────────────────────────────────────────────────────
    # Phase 2 will create these modules; we guard with try/except so the app
    # starts cleanly during Phase 1.
    _routers = [
        ("routes.auth", "/auth", "auth"),
        ("routes.dashboard", "/dashboard", "dashboard"),
        ("routes.seasons", "/seasons", "seasons"),
        ("routes.teams", "/teams", "teams"),
        ("routes.players", "/players", "players"),
        ("routes.events", "/events", "events"),
        ("routes.attendance", "/attendance", "attendance"),
        ("routes.reports", "/reports", "reports"),
        ("routes.users", "/auth/users", "users"),
        ("routes.telegram", "", "telegram"),
        ("routes.event_messages", "", "event_messages"),
        ("routes.absences", "", "absences"),
    ]
    for module_path, prefix, tag in _routers:
        try:
            import importlib

            module = importlib.import_module(module_path)
            app.include_router(module.router, prefix=prefix, tags=[tag])
        except ModuleNotFoundError:
            logger.debug("Router module %r not found — skipping (Phase 2).", module_path)

    # ── Notifications router ──────────────────────────────────────────────
    try:
        from routes import notifications as _notifications_mod  # noqa: PLC0415

        app.include_router(_notifications_mod.router)
    except ModuleNotFoundError:
        logger.debug("Notifications router not found — skipping.")

    # ── Locale switcher ───────────────────────────────────────────────────
    from routes.locale import router as _locale_router  # noqa: PLC0415

    app.include_router(_locale_router)

    # ── Profile page ──────────────────────────────────────────────────────
    from fastapi import Depends as _Depends  # noqa: PLC0415
    from sqlalchemy.orm import Session as _Session  # noqa: PLC0415

    from app.database import get_db as _get_db  # noqa: PLC0415
    from routes._auth_helpers import require_login as _require_login  # noqa: PLC0415

    @app.get("/profile", include_in_schema=False)
    async def profile_page(
        request: Request,
        user=_Depends(_require_login),
        db: _Session = _Depends(_get_db),
        flash: str = "",
    ):
        from models.notification_preference import NotificationPreference  # noqa: PLC0415
        from models.player import Player as _Player  # noqa: PLC0415
        from models.web_push_subscription import WebPushSubscription  # noqa: PLC0415

        current_player = db.query(_Player).filter(_Player.user_id == user.id, _Player.is_active.is_(True)).first()
        player_prefs: dict = {}
        push_device_count = 0
        if current_player:
            prefs = db.query(NotificationPreference).filter(NotificationPreference.player_id == current_player.id).all()
            player_prefs = {p.channel: p.enabled for p in prefs}
            push_device_count = (
                db.query(WebPushSubscription).filter(WebPushSubscription.player_id == current_player.id).count()
            )
        return render(
            request,
            "auth/profile.html",
            {
                "user": user,
                "current_player": current_player,
                "player_prefs": player_prefs,
                "push_device_count": push_device_count,
                "vapid_public_key": settings.VAPID_PUBLIC_KEY or None,
                "flash": flash,
            },
        )

    # ── Profile edit ──────────────────────────────────────────────────────
    from fastapi import Form as _Form  # noqa: PLC0415

    from app.csrf import require_csrf as _require_csrf  # noqa: PLC0415
    from services.auth_service import hash_password as _hash_password  # noqa: PLC0415
    from services.auth_service import verify_password as _verify_password

    @app.get("/profile/edit", include_in_schema=False)
    async def profile_edit_get(
        request: Request,
        user=_Depends(_require_login),
    ):
        return render(request, "auth/user_form.html", {"user": user, "target": user, "is_admin_edit": False, "error": None})

    @app.post("/profile/edit", include_in_schema=False)
    async def profile_edit_post(
        request: Request,
        user=_Depends(_require_login),
        _csrf=_Depends(_require_csrf),
        db: _Session = _Depends(_get_db),
        username: str = _Form(...),
        email: str = _Form(...),
        locale: str = _Form("en"),
        phone: str = _Form(""),
        first_name: str = _Form(""),
        last_name: str = _Form(""),
        current_password: str = _Form(""),
        new_password: str = _Form(""),
    ):
        from models.user import User as _User  # noqa: PLC0415
        from routes._auth_helpers import rt as _rt  # noqa: PLC0415

        username = username.strip()
        email = email.strip()

        def _error(msg: str):
            return render(request, "auth/user_form.html", {"user": user, "target": user, "is_admin_edit": False, "error": msg}, status_code=400)

        if not username:
            return _error(_rt(request, "errors.field_required", field="Username"))
        if not email:
            return _error(_rt(request, "errors.field_required", field="Email"))
        if new_password and not current_password:
            return _error(_rt(request, "errors.current_password_required"))
        if new_password and not _verify_password(current_password, user.hashed_password):
            return _error(_rt(request, "errors.current_password_wrong"))
        if new_password and len(new_password) < 8:
            return _error(_rt(request, "errors.password_too_short"))

        dup_user = db.query(_User).filter(_User.username == username, _User.id != user.id).first()
        if dup_user:
            return _error(_rt(request, "errors.username_taken", username=username))
        dup_email = db.query(_User).filter(_User.email == email, _User.id != user.id).first()
        if dup_email:
            return _error(_rt(request, "errors.email_taken", email=email))

        db_user = db.get(_User, user.id)
        db_user.username = username
        db_user.email = email
        db_user.locale = locale
        db_user.phone = phone.strip() or None
        db_user.first_name = first_name.strip() or None
        db_user.last_name = last_name.strip() or None
        if new_password:
            db_user.hashed_password = _hash_password(new_password)
        # Sync name to linked player if present
        for player in db_user.players:
            if db_user.first_name:
                player.first_name = db_user.first_name
            if db_user.last_name:
                player.last_name = db_user.last_name
        db.commit()
        from urllib.parse import quote as _quote  # noqa: PLC0415

        from routes._auth_helpers import rt as _rt2  # noqa: PLC0415
        flash = _quote(_rt2(request, "users.profile_saved"))
        from fastapi.responses import RedirectResponse as _RedirectResponse  # noqa: PLC0415
        return _RedirectResponse(f"/profile?flash={flash}", status_code=302)

    # ── Health check ──────────────────────────────────────────────────────
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return JSONResponse({"status": "ok"})

    # ── Root redirect ─────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard", status_code=302)

    # ── Auth exception handlers ───────────────────────────────────────────
    @app.exception_handler(NotAuthenticated)
    async def not_authenticated_handler(request: Request, exc: NotAuthenticated) -> RedirectResponse:
        return RedirectResponse("/auth/login", status_code=302)

    @app.exception_handler(NotAuthorized)
    async def not_authorized_handler(request: Request, exc: NotAuthorized) -> HTMLResponse:
        try:
            return render(
                request,
                "errors/403.html",
                {"user": request.state.user},
                status_code=403,
            )
        except Exception:
            return HTMLResponse("<h1>403 — Forbidden</h1>", status_code=403)

    # ── HTTP exception handlers ───────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc) -> HTMLResponse:
        try:
            return render(
                request,
                "errors/404.html",
                {"user": request.state.user},
                status_code=404,
            )
        except Exception:
            return HTMLResponse(content="<h1>404 — Page not found</h1>", status_code=404)

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc) -> HTMLResponse:
        logger.exception("Internal server error: %s", exc)
        try:
            return render(
                request,
                "errors/500.html",
                {"user": request.state.user},
                status_code=500,
            )
        except Exception:
            return HTMLResponse(content="<h1>500 — Internal Server Error</h1>", status_code=500)

    return app


# Top-level app instance — referenced by Uvicorn as "app.main:app"
app: FastAPI = create_app()
