"""routes/seasons.py — Season CRUD."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from models.season import Season
from routes._auth_helpers import require_admin, require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _parse_date(val: str):
    if not val or not val.strip():
        return None
    return datetime.strptime(val.strip(), "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def seasons_list(request: Request, db: Session = Depends(get_db)):
    result = require_login(request)
    if isinstance(result, Response):
        return result

    seasons = db.query(Season).order_by(Season.name).all()
    return templates.TemplateResponse(request, "seasons/list.html", {"user": request.state.user, "seasons": seasons})


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def season_new_get(request: Request):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user, "season": None, "error": None})


@router.post("/new")
async def season_new_post(
    request: Request,
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    if not name.strip():
        return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user,
                "season": None,
                "error": "Season name is required."}, 
            status_code=400)

    try:
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
    except ValueError:
        return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user,
                "season": None,
                "error": "Invalid date format. Use YYYY-MM-DD."}, 
            status_code=400)

    season = Season(name=name.strip(), start_date=s_date, end_date=e_date)
    db.add(season)
    db.commit()
    db.refresh(season)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.get("/{season_id}/edit")
async def season_edit_get(season_id: int, request: Request, db: Session = Depends(get_db)):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user, "season": season, "error": None})


@router.post("/{season_id}/edit")
async def season_edit_post(
    season_id: int,
    request: Request,
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    if not name.strip():
        return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user,
                "season": season,
                "error": "Season name is required."}, 
            status_code=400)

    try:
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
    except ValueError:
        return templates.TemplateResponse(request, "seasons/form.html", {"user": request.state.user,
                "season": season,
                "error": "Invalid date format. Use YYYY-MM-DD."}, 
            status_code=400)

    season.name = name.strip()
    season.start_date = s_date
    season.end_date = e_date
    db.add(season)
    db.commit()
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Activate
# ---------------------------------------------------------------------------


@router.post("/{season_id}/activate")
async def season_activate(season_id: int, request: Request, _csrf: None = Depends(require_csrf), db: Session = Depends(get_db)):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    # Deactivate all
    db.query(Season).update({"is_active": False})
    # Activate target
    season = db.get(Season, season_id)
    if season:
        season.is_active = True
        db.add(season)
    db.commit()
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.post("/{season_id}/delete")
async def season_delete(season_id: int, request: Request, _csrf: None = Depends(require_csrf), db: Session = Depends(get_db)):
    result = require_admin(request)
    if isinstance(result, Response):
        return result

    season = db.get(Season, season_id)
    if season:
        db.delete(season)
        db.commit()
    return RedirectResponse("/seasons", status_code=302)
