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
    yield
    logger.info("Shutting down.")
    shutdown_event.set()


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
            },
        )

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
