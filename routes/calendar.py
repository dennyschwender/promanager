# routes/calendar.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from models.user import User
from routes._auth_helpers import require_login
from services.calendar_service import build_ical_feed, generate_token

router = APIRouter()


@router.get("/{token}/feed.ics", include_in_schema=False)
async def calendar_feed(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.calendar_token == token).first()
    if not user:
        raise HTTPException(status_code=404)
    ical = build_ical_feed(user, db, settings.APP_URL, settings.APP_TIMEZONE)
    return Response(
        content=ical,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="promanager.ics"'},
    )


@router.post("/regenerate-token", include_in_schema=False, dependencies=[Depends(require_csrf)])
async def regenerate_token(
    request: Request,
    auth_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Re-fetch via the route's DB session so changes are visible to callers sharing the same session.
    user = db.get(User, auth_user.id)
    user.calendar_token = generate_token()
    db.commit()
    return RedirectResponse("/profile?flash=calendar_token_regenerated", status_code=302)
