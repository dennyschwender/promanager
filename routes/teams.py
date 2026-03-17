"""routes/teams.py — Team CRUD."""

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
from models.team import Team
from models.team_recurring_schedule import TeamRecurringSchedule
from models.user import User
from routes._auth_helpers import require_admin, require_login
from services.schedule_service import (
    count_future_events,
    delete_future_events,
    generate_events_for_schedule,
    is_changed,
    new_group_id,
    propagate_nonkey_changes,
    sign_payload,
    verify_payload,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _parse_schedule_rows(form, count: int) -> list[dict]:
    """Parse sched_* form fields into a list of raw string dicts."""
    rows = []
    for i in range(count):
        rows.append(
            {
                "id": (form.get(f"sched_id_{i}") or "").strip(),
                "title": (form.get(f"sched_title_{i}") or "").strip(),
                "event_type": (form.get(f"sched_event_type_{i}") or "training").strip(),
                "recurrence_rule": (form.get(f"sched_rule_{i}") or "weekly").strip(),
                "start_date": (form.get(f"sched_start_{i}") or "").strip(),
                "end_date": (form.get(f"sched_end_{i}") or "").strip(),
                "event_time": (form.get(f"sched_time_{i}") or "").strip(),
                "event_end_time": (form.get(f"sched_end_time_{i}") or "").strip(),
                "location": (form.get(f"sched_location_{i}") or "").strip(),
                "meeting_time": (form.get(f"sched_meeting_time_{i}") or "").strip(),
                "meeting_location": (form.get(f"sched_meeting_location_{i}") or "").strip(),
                "presence_type": (form.get(f"sched_presence_{i}") or "normal").strip(),
                "description": (form.get(f"sched_desc_{i}") or "").strip(),
                "season_id": (form.get(f"sched_season_{i}") or "").strip(),
            }
        )
    return rows


def _parse_dt(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_tm(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError:
        return None


def _schedule_to_dict(s: TeamRecurringSchedule) -> dict:
    return {
        "id": str(s.id),
        "title": s.title,
        "event_type": s.event_type,
        "recurrence_rule": s.recurrence_rule,
        "start_date": s.start_date.isoformat() if s.start_date else "",
        "end_date": s.end_date.isoformat() if s.end_date else "",
        "event_time": s.event_time.strftime("%H:%M") if s.event_time else "",
        "event_end_time": s.event_end_time.strftime("%H:%M") if s.event_end_time else "",
        "location": s.location or "",
        "meeting_time": s.meeting_time.strftime("%H:%M") if s.meeting_time else "",
        "meeting_location": s.meeting_location or "",
        "presence_type": s.presence_type,
        "description": s.description or "",
        "recurrence_group_id": s.recurrence_group_id,
        "season_id": str(s.season_id) if s.season_id else "",
    }


def _apply_row_to_schedule(sched: TeamRecurringSchedule, row: dict) -> None:
    sched.title = row["title"]
    sched.event_type = row["event_type"]
    sched.recurrence_rule = row["recurrence_rule"]
    sched.start_date = _parse_dt(row["start_date"])
    sched.end_date = _parse_dt(row["end_date"])
    sched.event_time = _parse_tm(row["event_time"])
    sched.event_end_time = _parse_tm(row["event_end_time"])
    sched.location = row["location"] or None
    sched.meeting_time = _parse_tm(row["meeting_time"])
    sched.meeting_location = row["meeting_location"] or None
    sched.presence_type = row["presence_type"]
    sched.description = row["description"] or None
    sid = row.get("season_id", "")
    sched.season_id = int(sid) if sid else None


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
    seasons = db.query(Season).order_by(Season.name).all()
    return render(request, "teams/list.html", {"user": user, "teams": teams, "seasons": seasons})


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def team_new_get(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "teams/form.html",
        {
            "user": user,
            "team": None,
            "seasons": db.query(Season).order_by(Season.name).all(),
            "error": None,
            "schedule_rows": [],
            "saved": False,
            "confirm_mode": False,
            "flagged": [],
            "_schedules_json": "",
        },
    )


@router.post("/new")
async def team_new_post(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if not name.strip():
        return render(
            request,
            "teams/form.html",
            {
                "user": user,
                "team": None,
                "error": "Team name is required.",
                "schedule_rows": [],
                "saved": False,
                "confirm_mode": False,
                "flagged": [],
                "_schedules_json": "",
            },
            status_code=400,
        )

    team = Team(
        name=name.strip(),
        description=description.strip() or None,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return RedirectResponse("/teams", status_code=302)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{team_id}")
async def team_detail(
    team_id: int,
    request: Request,
    saved: str = "",
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)
    return render(
        request,
        "teams/detail.html",
        {
            "user": user,
            "team": team,
            "schedules": team.recurring_schedules,
            "saved": saved == "1",
        },
    )


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.get("/{team_id}/edit")
async def team_edit_get(
    team_id: int,
    request: Request,
    saved: str = "",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    return render(
        request,
        "teams/form.html",
        {
            "user": user,
            "team": team,
            "seasons": db.query(Season).order_by(Season.name).all(),
            "schedule_rows": [_schedule_to_dict(s) for s in team.recurring_schedules],
            "error": None,
            "saved": saved == "1",
            "confirm_mode": False,
            "flagged": [],
            "_schedules_json": "",
        },
    )


@router.post("/{team_id}/edit")
async def team_edit_post(
    team_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    confirm_step: str = Form("", alias="_confirm_step"),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    form = await request.form()

    all_seasons = db.query(Season).order_by(Season.name).all()

    def _render(error=None, confirm_mode=False, flagged=None, schedule_rows=None, schedules_json="", saved=False):
        return render(
            request,
            "teams/form.html",
            {
                "user": user,
                "team": team,
                "seasons": all_seasons,
                "schedule_rows": (
                    schedule_rows
                    if schedule_rows is not None
                    else [_schedule_to_dict(s) for s in team.recurring_schedules]
                ),
                "error": error,
                "saved": saved,
                "confirm_mode": confirm_mode,
                "flagged": flagged or [],
                "_schedules_json": schedules_json,
            },
        )

    if not name.strip():
        return _render(error="Team name is required.")

    # Apply core team fields
    team.name = name.strip()
    team.description = description.strip() or None

    # ── CONFIRMATION POST ────────────────────────────────────────────────────
    if confirm_step == "1":
        raw_json = (form.get("_schedules_json") or "").strip()
        try:
            payload = verify_payload(raw_json)
        except ValueError:
            return _render(error="Invalid confirmation payload. Please try again.")

        # Verify team_id binding — prevents cross-team replay of a signed payload
        if payload.get("team_id") != team_id:
            return _render(error="Invalid confirmation payload. Please try again.")

        submitted_rows = payload.get("rows", [])
        stored_map = {s.id: s for s in team.recurring_schedules}
        submitted_ids = set()
        for r in submitted_rows:
            if r.get("id"):
                try:
                    submitted_ids.add(int(r["id"]))
                except ValueError:
                    pass

        for row in submitted_rows:
            sched_id_str = row.get("id", "")
            confirm_key = f"confirm_schedule_{sched_id_str or ('new_' + row.get('recurrence_group_id', ''))}"
            confirmed = form.get(confirm_key) == "on"

            if not sched_id_str:
                sched = TeamRecurringSchedule(
                    team_id=team_id,
                    recurrence_group_id=row.get("recurrence_group_id") or new_group_id(),
                )
                _apply_row_to_schedule(sched, row)
                db.add(sched)
                db.flush()
                try:
                    generate_events_for_schedule(db, sched, team)
                except ValueError:
                    pass
            else:
                try:
                    sched_id = int(sched_id_str)
                except ValueError:
                    continue
                sched = stored_map.get(sched_id)
                if sched is None:
                    continue
                if confirmed:
                    delete_future_events(db, sched.recurrence_group_id)
                    sched.recurrence_group_id = new_group_id()
                    _apply_row_to_schedule(sched, row)
                    db.add(sched)
                    db.flush()
                    try:
                        generate_events_for_schedule(db, sched, team)
                    except ValueError:
                        pass
                else:
                    # Determine if unchanged BEFORE mutating sched — is_changed
                    # compares stored ORM values vs submitted dict.
                    truly_unchanged = not is_changed(sched, row)
                    _apply_row_to_schedule(sched, row)
                    db.add(sched)
                    if truly_unchanged:
                        # Unchanged schedule: propagate non-key fields (title, description)
                        # in-place to future events, per spec.
                        propagate_nonkey_changes(
                            db,
                            sched.recurrence_group_id,
                            sched.title,
                            sched.description,
                        )
                    # else: changed-but-unchecked — save fields, do NOT touch events

        # Handle removed schedules
        for sched_id, sched in stored_map.items():
            if sched_id not in submitted_ids:
                confirm_key = f"confirm_schedule_{sched_id}"
                if form.get(confirm_key) == "on":
                    delete_future_events(db, sched.recurrence_group_id)
                    db.delete(sched)
                # else: keep schedule and events untouched

        try:
            db.add(team)
            db.commit()
        except Exception:
            db.rollback()
            # Note: db.rollback() cannot undo commits already made by ensure_attendance_records
            # inside generate_events_for_schedule. This is an accepted limitation.
            return _render(error="An error occurred saving the schedules. Please try again.")
        return RedirectResponse(f"/teams/{int(team_id)}?saved=1", status_code=302)

    # ── FIRST POST ───────────────────────────────────────────────────────────
    try:
        sched_count = int((form.get("sched_count") or "0").strip() or "0")
    except ValueError:
        sched_count = 0
    submitted_rows = _parse_schedule_rows(form, sched_count)

    stored = team.recurring_schedules
    stored_map = {s.id: s for s in stored}
    submitted_ids = set()
    for r in submitted_rows:
        if r["id"]:
            try:
                submitted_ids.add(int(r["id"]))
            except ValueError:
                pass

    flagged = []
    new_rows = []
    unchanged_rows = []

    for row in submitted_rows:
        if not row["title"]:
            continue
        sched_id_str = row["id"]

        if not sched_id_str:
            row["recurrence_group_id"] = new_group_id()
            new_rows.append(row)
        else:
            try:
                sched_id = int(sched_id_str)
            except ValueError:
                continue
            stored_sched = stored_map.get(sched_id)
            if stored_sched is None:
                continue
            if is_changed(stored_sched, row):
                future_count = count_future_events(db, stored_sched.recurrence_group_id)
                flagged.append(
                    {
                        "type": "changed",
                        "sched_id": sched_id,
                        "title": row["title"],
                        "future_count": future_count,
                        "confirm_key": f"confirm_schedule_{sched_id}",
                        "row": row,
                    }
                )
            else:
                unchanged_rows.append((stored_sched, row))

    for sched_id, sched in stored_map.items():
        if sched_id not in submitted_ids:
            future_count = count_future_events(db, sched.recurrence_group_id)
            flagged.append(
                {
                    "type": "removed",
                    "sched_id": sched_id,
                    "title": sched.title,
                    "future_count": future_count,
                    "confirm_key": f"confirm_schedule_{sched_id}",
                    "row": _schedule_to_dict(sched),
                }
            )

    if flagged:
        # Bind team_id into the payload to prevent cross-team replay attacks.
        # Filter empty-title rows: they were already skipped in the first-POST loop
        # and must not be re-processed on the confirm POST.
        payload_data = {"team_id": team_id, "rows": [r for r in submitted_rows if r["title"]]}
        signed = sign_payload(payload_data)
        return _render(
            confirm_mode=True,
            flagged=flagged,
            schedule_rows=[r for r in submitted_rows if r["title"]],
            schedules_json=signed,
        )

    # No confirmation needed — apply everything in a single transaction
    for row in new_rows:
        sched = TeamRecurringSchedule(
            team_id=team_id,
            recurrence_group_id=row["recurrence_group_id"],
        )
        _apply_row_to_schedule(sched, row)
        db.add(sched)
        db.flush()
        try:
            generate_events_for_schedule(db, sched, team)
        except ValueError:
            pass

    for stored_sched, row in unchanged_rows:
        _apply_row_to_schedule(stored_sched, row)
        propagate_nonkey_changes(
            db,
            stored_sched.recurrence_group_id,
            stored_sched.title,
            stored_sched.description,
        )
        db.add(stored_sched)

    try:
        db.add(team)
        db.commit()
    except Exception:
        db.rollback()
        # Note: db.rollback() cannot undo commits already made by ensure_attendance_records
        # inside generate_events_for_schedule. This is an accepted limitation.
        return _render(error="An error occurred saving the schedules. Please try again.")
    return RedirectResponse(f"/teams/{int(team_id)}?saved=1", status_code=302)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Copy roster
# ---------------------------------------------------------------------------


@router.post("/{team_id}/copy-roster")
async def team_copy_roster(
    team_id: int,
    request: Request,
    source_season_id: int = Form(...),
    target_season_id: int = Form(...),
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if source_season_id == target_season_id:
        return RedirectResponse("/teams?copy_error=same_season", status_code=302)

    source_rows = (
        db.query(PlayerTeam)
        .filter(PlayerTeam.team_id == team_id, PlayerTeam.season_id == source_season_id)
        .all()
    )
    existing = {
        pt.player_id
        for pt in db.query(PlayerTeam)
        .filter(PlayerTeam.team_id == team_id, PlayerTeam.season_id == target_season_id)
        .all()
    }
    for src in source_rows:
        if src.player_id in existing:
            continue
        db.add(PlayerTeam(
            player_id=src.player_id,
            team_id=team_id,
            season_id=target_season_id,
            priority=src.priority,
            role=src.role,
            position=src.position,
            shirt_number=src.shirt_number,
            membership_status=src.membership_status,
            injured_until=None,
            absent_by_default=False,
        ))
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
