"""routes/seasons.py — Season CRUD."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.templates import render
from models.player_team import PlayerTeam
from models.season import Season
from models.user import User
from routes._auth_helpers import require_admin, require_coach_or_admin, rt
from services.audit_service import log_action

router = APIRouter()


def _parse_date(val: str):
    if not val or not val.strip():
        return None
    return datetime.strptime(val.strip(), "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def seasons_list(
    request: Request,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    return render(request, "seasons/list.html", {"user": user, "seasons": seasons})


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def season_new_get(request: Request, user: User = Depends(require_admin)):
    return render(
        request,
        "seasons/form.html",
        {
            "user": user,
            "season": None,
            "error": None,
        },
    )


@router.post("/new")
async def season_new_post(
    request: Request,
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if not name.strip():
        return render(
            request,
            "seasons/form.html",
            {
                "user": user,
                "season": None,
                "error": rt(request, "errors.field_required", field="Season name"),
            },
            status_code=400,
        )

    try:
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
    except ValueError:
        return render(
            request,
            "seasons/form.html",
            {
                "user": user,
                "season": None,
                "error": rt(request, "errors.invalid_date_format"),
            },
            status_code=400,
        )

    season = Season(name=name.strip(), start_date=s_date, end_date=e_date)
    db.add(season)
    db.commit()
    db.refresh(season)
    log_action("season.create", target_type="season", target_id=season.id, target_label=season.name, request=request)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.get("/{season_id}/edit")
async def season_edit_get(
    season_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)
    return render(
        request,
        "seasons/form.html",
        {
            "user": user,
            "season": season,
            "error": None,
        },
    )


@router.post("/{season_id}/edit")
async def season_edit_post(
    season_id: int,
    request: Request,
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season is None:
        return RedirectResponse("/seasons", status_code=302)

    if not name.strip():
        return render(
            request,
            "seasons/form.html",
            {
                "user": user,
                "season": season,
                "error": rt(request, "errors.field_required", field="Season name"),
            },
            status_code=400,
        )

    try:
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
    except ValueError:
        return render(
            request,
            "seasons/form.html",
            {
                "user": user,
                "season": season,
                "error": rt(request, "errors.invalid_date_format"),
            },
            status_code=400,
        )

    season.name = name.strip()
    season.start_date = s_date
    season.end_date = e_date
    db.add(season)
    db.commit()
    log_action("season.update", target_type="season", target_id=season.id, target_label=season.name, request=request)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Activate
# ---------------------------------------------------------------------------


@router.post("/{season_id}/activate")
async def season_activate(
    season_id: int,
    request: Request,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    db.query(Season).update({"is_active": False})
    season = db.get(Season, season_id)
    if season:
        season.is_active = True
        db.add(season)
    db.commit()
    if season:
        log_action("season.activate", target_type="season", target_id=season.id, target_label=season.name, request=request)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.post("/{season_id}/delete")
async def season_delete(
    season_id: int,
    request: Request,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    season = db.get(Season, season_id)
    if season:
        label = season.name
        db.delete(season)
        db.commit()
        log_action("season.delete", target_type="season", target_id=season_id, target_label=label, request=request)
    return RedirectResponse("/seasons", status_code=302)


# ---------------------------------------------------------------------------
# Copy roster
# ---------------------------------------------------------------------------


@router.post("/{season_id}/copy-roster")
async def season_copy_roster(
    season_id: int,
    request: Request,
    source_season_id: int = Form(...),
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if source_season_id == season_id:
        return render(
            request,
            "seasons/list.html",
            {
                "user": _user,
                "seasons": db.query(Season).order_by(Season.name).all(),
                "error": rt(request, "errors.same_season"),
            },
            status_code=400,
        )

    target = db.get(Season, season_id)
    source = db.get(Season, source_season_id)
    if target is None or source is None:
        return RedirectResponse("/seasons", status_code=302)

    # Fetch all memberships from source season
    source_memberships = db.query(PlayerTeam).filter(PlayerTeam.season_id == source_season_id).all()

    # Find existing (player_id, team_id) pairs in target to skip duplicates
    existing = {
        (pt.player_id, pt.team_id) for pt in db.query(PlayerTeam).filter(PlayerTeam.season_id == season_id).all()
    }

    copied = 0
    for src in source_memberships:
        if (src.player_id, src.team_id) in existing:
            continue
        db.add(
            PlayerTeam(
                player_id=src.player_id,
                team_id=src.team_id,
                season_id=season_id,
                priority=src.priority,
                role=src.role,
                position=src.position,
                shirt_number=src.shirt_number,
                membership_status=src.membership_status,
                injured_until=None,  # stale from prior season — reset
                absent_by_default=False,  # stale from prior season — reset
            )
        )
        copied += 1

    db.commit()
    return RedirectResponse(f"/seasons?copied={copied}", status_code=302)
