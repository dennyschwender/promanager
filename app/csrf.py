"""app/csrf.py — CSRF token helpers (synchronizer-token pattern).

The token is an HMAC-SHA256 of the session cookie value keyed by SECRET_KEY.
This ties the token to the user's session without any server-side state.
"""
from __future__ import annotations

import hmac
import hashlib

from fastapi import HTTPException, Request

from app.config import settings

COOKIE_NAME = "session_user_id"


def _compute(session_cookie: str) -> str:
    key = settings.SECRET_KEY.encode()
    msg = f"csrf:{session_cookie or 'anon'}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def generate_csrf_token(session_cookie: str = "") -> str:
    """Return the CSRF token for the given session cookie value."""
    return _compute(session_cookie)


def verify_csrf_token(token: str, session_cookie: str = "") -> bool:
    """Return True iff *token* is the correct CSRF token for *session_cookie*."""
    if not token:
        return False
    expected = _compute(session_cookie)
    return hmac.compare_digest(token, expected)


async def require_csrf(request: Request) -> None:
    """FastAPI dependency: raise 403 if the CSRF token in the form body is invalid."""
    form = await request.form()
    token = str(form.get("csrf_token", ""))
    session_cookie = request.cookies.get(COOKIE_NAME, "")
    if not verify_csrf_token(token, session_cookie):
        raise HTTPException(
            status_code=403,
            detail="CSRF token invalid or missing. Please go back and try again.",
        )
