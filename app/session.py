"""app/session.py — Session cookie helpers shared across the app."""

from __future__ import annotations

from datetime import timezone

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

import app.database as _db_mod
from app.config import settings

COOKIE_NAME = "session_user_id"
_signer = TimestampSigner(settings.SECRET_KEY)


def create_session_cookie(user_id: int) -> str:
    """Return a signed, timestamped cookie value for the given user_id."""
    return _signer.sign(str(user_id).encode()).decode()


def get_user_from_cookie(request: Request):
    """Return the User ORM object for the signed session cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        raw, ts = _signer.unsign(token, max_age=60 * 60 * 24 * 7, return_timestamp=True)
        user_id = int(raw.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None

    from models.user import User  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        # Check if all sessions have been invalidated since this cookie was issued
        if user.logout_all_at is not None and ts is not None:
            cookie_ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            if cookie_ts < user.logout_all_at:
                return None
        return user
    finally:
        db.close()
