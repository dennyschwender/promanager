"""routes/teams.py — Team CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from app.templates import templates
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import require_admin, require_login

router = APIRouter()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def teams_list(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    teams = db.query(Team).order_by(Team.name).all()
    return templates.TemplateResponse(request, "teams/list.html", {"user": user, "teams": teams})


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def team_new_get(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    return templates.TemplateResponse(request, "teams/form.html", {
        "user": user,
        "team": None,
        "seasons": seasons,
        "error": None,
    })


@router.post("/new")
async def team_new_post(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    season_id: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if not name.strip():
        seasons = db.query(Season).order_by(Season.name).all()
        return templates.TemplateResponse(request, "teams/form.html", {
            "user": user,
            "team": None,
            "seasons": seasons,
            "error": "Team name is required.",
        }, status_code=400)

    sid = int(season_id) if season_id.strip() else None
    team = Team(
        name=name.strip(),
        description=description.strip() or None,
        season_id=sid,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return RedirectResponse("/teams", status_code=302)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.get("/{team_id}/edit")
async def team_edit_get(
    team_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    seasons = db.query(Season).order_by(Season.name).all()
    return templates.TemplateResponse(request, "teams/form.html", {
        "user": user,
        "team": team,
        "seasons": seasons,
        "error": None,
    })


@router.post("/{team_id}/edit")
async def team_edit_post(
    team_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    season_id: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    if not name.strip():
        seasons = db.query(Season).order_by(Season.name).all()
        return templates.TemplateResponse(request, "teams/form.html", {
            "user": user,
            "team": team,
            "seasons": seasons,
            "error": "Team name is required.",
        }, status_code=400)

    team.name = name.strip()
    team.description = description.strip() or None
    team.season_id = int(season_id) if season_id.strip() else None
    db.add(team)
    db.commit()
    return RedirectResponse("/teams", status_code=302)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.post("/{team_id}/delete")
async def team_delete(
    team_id: int,
    request: Request,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team:
        db.delete(team)
        db.commit()
    return RedirectResponse("/teams", status_code=302)
