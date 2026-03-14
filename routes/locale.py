"""routes/locale.py — Language preference endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.i18n import SUPPORTED_LOCALES

router = APIRouter(tags=["locale"])


def _safe_next(next_url: str) -> str:
    """Return next_url only if it is a safe relative path."""
    if next_url and next_url.startswith("/") and "://" not in next_url:
        return next_url
    return "/dashboard"


@router.post("/set-locale")
async def set_locale(
    request: Request,
    locale: str = Form(...),
    next: str = Form(default="/dashboard"),
    db: Session = Depends(get_db),
):
    if locale not in SUPPORTED_LOCALES:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Unsupported locale"}, status_code=400)

    redirect_to = _safe_next(next)
    response = RedirectResponse(url=redirect_to, status_code=302)
    response.set_cookie("locale", locale, max_age=31536000, path="/", httponly=False)

    # Persist to DB if authenticated
    user = getattr(request.state, "user", None)
    if user is not None:
        merged = db.merge(user)
        merged.locale = locale
        db.commit()

    return response
