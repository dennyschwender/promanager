"""app/main.py — FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime as _dt, timezone as _tz
from typing import AsyncIterator
from urllib.parse import quote_plus as _quote_plus

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings
from app.csrf import generate_csrf_token
from app.database import SessionLocal, init_db
from app.limiter import limiter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 templates (shared with routes via import)
# ---------------------------------------------------------------------------
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: _dt.now(_tz.utc)
templates.env.filters["urlencode"] = _quote_plus

# ---------------------------------------------------------------------------
# Session / auth helpers
# ---------------------------------------------------------------------------
COOKIE_NAME = "session_user_id"
_signer = TimestampSigner(settings.SECRET_KEY)


def _get_user_from_cookie(request: Request):
    """Return the User ORM object for the signed session cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        raw: bytes = _signer.unsign(token, max_age=60 * 60 * 24 * 7)  # 7 days
        user_id = int(raw.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None

    # Late import to avoid circular imports at module load time
    from models.user import User  # noqa: PLC0415

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Middleware — inject request.state.user
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Reads the signed session cookie and attaches the User to request.state."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.user = _get_user_from_cookie(request)
        request.state.csrf_token = generate_csrf_token(
            request.cookies.get(COOKIE_NAME, "")
        )
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
            "Generate a new one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    logger.info("Starting up — initialising database …")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


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
    app.add_middleware(AuthMiddleware)

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
    ]
    for module_path, prefix, tag in _routers:
        try:
            import importlib

            module = importlib.import_module(module_path)
            app.include_router(module.router, prefix=prefix, tags=[tag])
        except ModuleNotFoundError:
            logger.debug("Router module %r not found — skipping (Phase 2).", module_path)

    # ── Root redirect ─────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard", status_code=302)

    # ── Exception handlers ────────────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc) -> HTMLResponse:
        try:
            return templates.TemplateResponse(
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
            return templates.TemplateResponse(
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
