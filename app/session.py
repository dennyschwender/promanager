"""app/session.py — Session cookie helpers shared across the app."""

from __future__ import annotations

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

import app.database as _db_mod
from app.config import settings

COOKIE_NAME = "session_user_id"
_signer = TimestampSigner(settings.SECRET_KEY)


def get_user_from_cookie(request: Request):
    """Return the User ORM object for the signed session cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        raw: bytes = _signer.unsign(token, max_age=60 * 60 * 24 * 7)  # 7 days
        user_id = int(raw.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None

    from models.user import User  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user
    finally:
        db.close()
