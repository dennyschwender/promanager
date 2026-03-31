"""routes/players.py — Player CRUD."""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.csrf import require_csrf, require_csrf_header
from app.database import get_db
from app.templates import render
from models.player import Player
from models.player_contact import PlayerContact
from models.player_phone import PlayerPhone
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import check_team_access, require_admin, require_coach_or_admin, require_login, rt
from services.attendance_service import backfill_attendance_for_player, get_player_attendance_history
from services.import_service import ImportResult, parse_csv, parse_xlsx, process_rows

router = APIRouter()


# ---------------------------------------------------------------------------
# Form-parsing helpers
# ---------------------------------------------------------------------------


def _parse_team_memberships(form) -> list[tuple[int, int, dict]]:
    """Return list of (team_id, priority, extra_fields) from form data.

    extra_fields keys: role, position, shirt_number, membership_status, injured_until,
    absent_by_default. Supports the new multi-checkbox UI or legacy single team_id.
    """
    raw_ids = form.getlist("team_ids")
    if raw_ids:
        result = []
        for tid_str in raw_ids:
            try:
                tid = int(tid_str)
            except (ValueError, TypeError):
                continue
            try:
                priority = int(form.get(f"priority_{tid}", 1))
            except (ValueError, TypeError):
                priority = 1
            shirt_raw = form.get(f"shirt_{tid}", "").strip()
            injured_raw = form.get(f"injured_until_{tid}", "").strip()
            extra = {
                "role": (form.get(f"role_{tid}") or "player").strip(),
                "position": (form.get(f"position_{tid}") or "").strip() or None,
                "shirt_number": int(shirt_raw) if shirt_raw.isdigit() else None,
                "membership_status": (form.get(f"status_{tid}") or "active").strip(),
                "injured_until": _parse_date(injured_raw),
                "absent_by_default": form.get(f"absent_default_{tid}") in ("on", "1", "true", "yes"),
            }
            result.append((tid, max(1, priority), extra))
        return result

    # Legacy single team_id (used by tests)
    tid_str = form.get("team_id", "")
    if tid_str and tid_str.strip():
        return [(int(tid_str.strip()), 1, {})]
    return []


def _sync_memberships(
    db: Session,
    player: Player,
    memberships: list[tuple[int, int, dict]],
    season_id: int,
) -> None:
    """Replace PlayerTeam rows for *player* in *season* with *memberships*.
    Memberships from other seasons are untouched.
    Backfills attendance records for newly added teams.
    """
    # Capture existing team_ids before deletion so we know what's new
    existing_team_ids = {
        pt.team_id
        for pt in db.query(PlayerTeam)
        .filter(
            PlayerTeam.player_id == player.id,
            PlayerTeam.season_id == season_id,
        )
        .all()
    }

    db.query(PlayerTeam).filter(
        PlayerTeam.player_id == player.id,
        PlayerTeam.season_id == season_id,
    ).delete()

    new_team_ids: list[int] = []
    for team_id, priority, extra in memberships:
        db.add(
            PlayerTeam(
                player_id=player.id,
                team_id=team_id,
                season_id=season_id,
                priority=priority,
                role=extra.get("role", "player") or "player",
                position=extra.get("position"),
                shirt_number=extra.get("shirt_number"),
                membership_status=extra.get("membership_status", "active") or "active",
                injured_until=extra.get("injured_until"),
                absent_by_default=bool(extra.get("absent_by_default", False)),
            )
        )
        if team_id not in existing_team_ids:
            new_team_ids.append(team_id)

    # Flush so the new PlayerTeam rows are visible for the backfill queries
    db.flush()

    for team_id in new_team_ids:
        backfill_attendance_for_player(db, player.id, team_id, season_id)


def _parse_date(value: str) -> date | None:
    """Parse ISO date string, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _sync_phones(db: Session, player: Player, form) -> None:
    """Rebuild PlayerPhone records from phone_N / phone_label_N form fields."""
    db.query(PlayerPhone).filter(PlayerPhone.player_id == player.id).delete()
    for i in range(1, 11):
        number = (form.get(f"phone_{i}") or "").strip()
        if not number:
            continue
        label = (form.get(f"phone_label_{i}") or "").strip() or None
        db.add(PlayerPhone(player_id=player.id, phone=number, label=label))


def _sync_contact(db: Session, player: Player, form) -> None:
    """Upsert PlayerContact record from contact_* form fields."""
    first = (form.get("contact_first_name") or "").strip()
    last = (form.get("contact_last_name") or "").strip()
    # If both names are blank, remove existing contact
    if not first and not last:
        db.query(PlayerContact).filter(PlayerContact.player_id == player.id).delete()
        return

    contact = db.query(PlayerContact).filter(PlayerContact.player_id == player.id).first()
    if contact is None:
        contact = PlayerContact(player_id=player.id)
        db.add(contact)

    contact.first_name = first
    contact.last_name = last
    contact.relationship_label = (form.get("contact_relationship") or "").strip() or None
    contact.email = (form.get("contact_email") or "").strip() or None
    contact.phone = (form.get("contact_phone") or "").strip() or None
    contact.phone2 = (form.get("contact_phone2") or "").strip() or None
    contact.street = (form.get("contact_street") or "").strip() or None
    contact.postcode = (form.get("contact_postcode") or "").strip() or None
    contact.city = (form.get("contact_city") or "").strip() or None


def _apply_personal_fields(player: Player, form) -> None:
    """Write personal-info form values onto a Player instance."""
    player.sex = (form.get("sex") or "").strip() or None
    player.date_of_birth = _parse_date((form.get("date_of_birth") or "").strip())
    player.street = (form.get("street") or "").strip() or None
    player.postcode = (form.get("postcode") or "").strip() or None
    player.city = (form.get("city") or "").strip() or None


def _active_season_id(db: Session) -> int | None:
    season = db.query(Season).filter(Season.is_active == True).first()  # noqa: E712
    return season.id if season else None


def _memberships_dict(player: Player, season_id: int | None) -> dict:
    """Return {team_id: PlayerTeam} for pre-filling the edit form, scoped to season."""
    if season_id is None:
        return {}
    return {m.team_id: m for m in player.team_memberships if m.season_id == season_id}


def _all_memberships_dict(player: Player) -> dict:
    """Return {season_id: {team_id: PlayerTeam}} for all seasons."""
    result: dict = {}
    for m in player.team_memberships:
        result.setdefault(m.season_id, {})[m.team_id] = m
    return result


def _parse_team_memberships_for_season(form, season_id: int) -> list[tuple[int, int, dict]]:
    """Like _parse_team_memberships but reads season-scoped field names."""
    raw_ids = form.getlist(f"team_ids_{season_id}")
    result = []
    for tid_str in raw_ids:
        try:
            tid = int(tid_str)
        except (ValueError, TypeError):
            continue
        try:
            priority = int(form.get(f"priority_{season_id}_{tid}", 1))
        except (ValueError, TypeError):
            priority = 1
        shirt_raw = form.get(f"shirt_{season_id}_{tid}", "").strip()
        injured_raw = form.get(f"injured_until_{season_id}_{tid}", "").strip()
        extra = {
            "role": (form.get(f"role_{season_id}_{tid}") or "player").strip(),
            "position": (form.get(f"position_{season_id}_{tid}") or "").strip() or None,
            "shirt_number": int(shirt_raw) if shirt_raw.isdigit() else None,
            "membership_status": (form.get(f"status_{season_id}_{tid}") or "active").strip(),
            "injured_until": _parse_date(injured_raw),
            "absent_by_default": form.get(f"absent_default_{season_id}_{tid}") in ("on", "1", "true", "yes"),
        }
        result.append((tid, max(1, priority), extra))
    return result


# ---------------------------------------------------------------------------
# Bulk assign
# ---------------------------------------------------------------------------


class BulkAssignRequest(BaseModel):
    player_ids: list[int]
    team_id: int
    season_id: int


@router.post("/bulk-assign")
async def player_bulk_assign(
    body: BulkAssignRequest,
    user: User = Depends(require_coach_or_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    check_team_access(user, body.team_id, db)
    assigned = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        existing = db.get(PlayerTeam, (pid, body.team_id, body.season_id))
        if existing:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()  # savepoint — failure here won't roll back prior rows
            db.add(
                PlayerTeam(
                    player_id=pid,
                    team_id=body.team_id,
                    season_id=body.season_id,
                )
            )
            sp.commit()
            assigned += 1
            backfill_attendance_for_player(db, pid, body.team_id, body.season_id)
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not assign player (database error)."})
    db.commit()
    return {"assigned": assigned, "skipped": skipped, "errors": errors}


class BulkRemoveRequest(BaseModel):
    player_ids: list[int]
    team_id: int
    season_id: int


@router.post("/bulk-remove")
async def player_bulk_remove(
    body: BulkRemoveRequest,
    user: User = Depends(require_coach_or_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    check_team_access(user, body.team_id, db)
    removed = 0
    skipped = 0
    for pid in body.player_ids:
        existing = db.get(PlayerTeam, (pid, body.team_id, body.season_id))
        if not existing:
            skipped += 1
            continue
        db.delete(existing)
        removed += 1
    db.commit()
    return {"removed": removed, "skipped": skipped}


# ── Allowed fields per model ───────────────────────────────────────────────
# All of these exist as mapped columns on Player (verified against models/player.py).
_PLAYER_FIELDS = frozenset(
    {
        "email",
        "phone",
        "is_active",
        "date_of_birth",
        "sex",
        "street",
        "postcode",
        "city",
    }
)
_PT_FIELDS = frozenset(
    {
        "shirt_number",
        "position",
        "injured_until",
        "absent_by_default",
        "priority",
    }
)


class PlayerDiff(BaseModel):
    id: int
    model_config = {"extra": "allow"}


class BulkUpdateRequest(BaseModel):
    players: list[PlayerDiff]
    season_id: int | None = None
    team_id: int | None = None


@router.post("/bulk-update")
async def player_bulk_update(
    body: BulkUpdateRequest,
    user: User = Depends(require_coach_or_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    if body.team_id is not None:
        check_team_access(user, body.team_id, db)

    saved: list[int] = []
    errors: list[dict] = []

    # Reject early if PlayerTeam fields are present but team_id is missing
    pt_keys_present = any(bool(_PT_FIELDS & set((diff.model_extra or {}).keys())) for diff in body.players)
    if pt_keys_present and body.team_id is None:
        raise HTTPException(
            status_code=400,
            detail="team_id is required when updating PlayerTeam fields.",
        )

    # Reject unknown fields early
    all_known = _PLAYER_FIELDS | _PT_FIELDS
    for diff in body.players:
        unknown = set((diff.model_extra or {}).keys()) - all_known
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown field(s): {', '.join(sorted(unknown))}",
            )

    for diff in body.players:
        extra = diff.model_extra or {}
        # Coaches may only update PT-fields (team-scoped); player-level fields are admin-only
        if not user.is_admin:
            extra = {k: v for k, v in extra.items() if k in _PT_FIELDS}
        player_changes = {k: v for k, v in extra.items() if k in _PLAYER_FIELDS}
        pt_changes = {k: v for k, v in extra.items() if k in _PT_FIELDS}

        # ── Shirt number uniqueness check (exclude self) ──────────────────
        if "shirt_number" in pt_changes and pt_changes["shirt_number"] is not None:
            conflict = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.team_id == body.team_id,
                    PlayerTeam.season_id == body.season_id,
                    PlayerTeam.shirt_number == pt_changes["shirt_number"],
                    PlayerTeam.player_id != diff.id,
                )
                .first()
            )
            if conflict:
                errors.append(
                    {
                        "id": diff.id,
                        "message": (f"Shirt number {pt_changes['shirt_number']} already taken in this team/season."),
                    }
                )
                continue

        try:
            sp = db.begin_nested()  # savepoint — isolates this row from others

            player = db.get(Player, diff.id)
            if player is None:
                sp.rollback()
                errors.append({"id": diff.id, "message": "Player not found."})
                continue

            # Apply Player-level fields
            for field, value in player_changes.items():
                if field == "date_of_birth" and isinstance(value, str) and value:
                    try:
                        value = date.fromisoformat(value)
                    except ValueError:
                        value = None
                setattr(player, field, value)

            # Apply PlayerTeam fields (upsert)
            if pt_changes:
                pt = db.get(PlayerTeam, (diff.id, body.team_id, body.season_id))
                if pt is None:
                    pt = PlayerTeam(
                        player_id=diff.id,
                        team_id=body.team_id,
                        season_id=body.season_id,
                    )
                    db.add(pt)
                for field, value in pt_changes.items():
                    if field == "injured_until" and isinstance(value, str) and value:
                        try:
                            value = date.fromisoformat(value)
                        except ValueError:
                            value = None
                    setattr(pt, field, value)

            sp.commit()
            saved.append(diff.id)

        except Exception:
            sp.rollback()
            errors.append({"id": diff.id, "message": "Could not update player (database error)."})

    db.commit()
    return {"saved": saved, "errors": errors}


# ── Bulk archive / activate ───────────────────────────────────────────────


class BulkPlayerIdsRequest(BaseModel):
    player_ids: list[int]


@router.post("/bulk-archive")
async def player_bulk_archive(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    archived = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.archived_at = datetime.now(timezone.utc)
            sp.commit()
            archived += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not archive player."})
    db.commit()
    return {"archived": archived, "skipped": skipped, "errors": errors}


@router.post("/bulk-unarchive")
async def player_bulk_unarchive(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    unarchived = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.archived_at is None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.archived_at = None
            sp.commit()
            unarchived += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not unarchive player."})
    db.commit()
    return {"unarchived": unarchived, "skipped": skipped, "errors": errors}


@router.post("/bulk-activate")
async def player_bulk_activate(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    activated = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.is_active or player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.is_active = True
            sp.commit()
            activated += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not activate player."})
    db.commit()
    return {"activated": activated, "skipped": skipped, "errors": errors}


@router.post("/bulk-deactivate")
async def player_bulk_deactivate(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    deactivated = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if not player.is_active or player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.is_active = False
            sp.commit()
            deactivated += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not deactivate player."})
    db.commit()
    return {"deactivated": deactivated, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def players_list(
    request: Request,
    team_id: int | None = None,
    season_id: int | None = None,
    archived: str | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = season_id

    q = db.query(Player)
    # Archive filter
    if archived == "only":
        q = q.filter(Player.archived_at.isnot(None))
    elif archived == "all":
        pass  # no filter
    else:  # default (None, empty string, or unrecognized value): show active only
        q = q.filter(Player.archived_at.is_(None))
    if team_id is not None and selected_season_id is not None:
        q = q.join(PlayerTeam, Player.id == PlayerTeam.player_id).filter(
            PlayerTeam.team_id == team_id, PlayerTeam.season_id == selected_season_id
        )
    elif team_id is not None:
        q = q.join(PlayerTeam, Player.id == PlayerTeam.player_id).filter(PlayerTeam.team_id == team_id)
    players = q.order_by(Player.last_name, Player.first_name).all()
    teams = db.query(Team).order_by(Team.name).all()

    # Build {player_id: PlayerTeam} for the template (requires both filters set)
    player_team_map: dict = {}
    if selected_season_id is not None and team_id is not None:
        pts = (
            db.query(PlayerTeam)
            .filter(
                PlayerTeam.season_id == selected_season_id,
                PlayerTeam.team_id == team_id,
                PlayerTeam.player_id.in_([p.id for p in players]),
            )
            .all()
        )
        player_team_map = {pt.player_id: pt for pt in pts}

    return render(
        request,
        "players/list.html",
        {
            "user": user,
            "players": players,
            "teams": teams,
            "seasons": seasons,
            "selected_team_id": team_id,
            "selected_season_id": selected_season_id,
            "player_team_map": player_team_map,
            "archived_filter": archived or "",
        },
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new")
async def player_new_get(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    return render(
        request,
        "players/form.html",
        {
            "user": user,
            "player": None,
            "teams": teams,
            "users": users,
            "seasons": seasons,
            "active_season_id": _active_season_id(db),
            "all_memberships": {},
            "error": None,
        },
    )


@router.post("/new")
async def player_new_post(
    request: Request,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form = await request.form()
    first_name = (form.get("first_name") or "").strip()
    last_name = (form.get("last_name") or "").strip()
    email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip()
    user_id_s = (form.get("user_id") or "").strip()

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()

    if not first_name or not last_name:
        return render(
            request,
            "players/form.html",
            {
                "user": user,
                "player": None,
                "teams": teams,
                "users": users,
                "seasons": seasons,
                "active_season_id": _active_season_id(db),
                "all_memberships": {},
                "error": rt(request, "errors.name_required"),
            },
            status_code=400,
        )

    parsed_user_id = int(user_id_s) if user_id_s else None
    if parsed_user_id is not None:
        conflict = db.query(Player).filter(Player.user_id == parsed_user_id).first()
        if conflict:
            return render(
                request,
                "players/form.html",
                {
                    "user": user,
                    "player": None,
                    "teams": teams,
                    "users": users,
                    "seasons": seasons,
                    "active_season_id": _active_season_id(db),
                    "all_memberships": {},
                    "error": rt(request, "errors.user_already_linked"),
                },
                status_code=400,
            )

    player = Player(
        first_name=first_name,
        last_name=last_name,
        email=email or None,
        phone=phone or None,
        user_id=parsed_user_id,
        is_active=True,
    )
    _apply_personal_fields(player, form)
    db.add(player)
    db.flush()

    for s in seasons:
        _sync_memberships(db, player, _parse_team_memberships_for_season(form, s.id), season_id=s.id)
    _sync_phones(db, player, form)
    _sync_contact(db, player, form)

    db.commit()
    return RedirectResponse("/players", status_code=302)


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

IMPORT_COLUMNS = [
    "first_name",
    "last_name",
    "email",
    "phone",
    "sex",
    "date_of_birth",
    "street",
    "postcode",
    "city",
]


@router.get("/import")
async def player_import_get(
    request: Request,
    team_id: int | None = None,
    season_id: int | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    context_team = db.get(Team, team_id) if team_id else None
    all_teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = season_id or (_active_season_id(db) if team_id else None)
    return render(
        request,
        "players/import.html",
        {
            "user": user,
            "context_team": context_team,
            "all_teams": all_teams,
            "seasons": seasons,
            "selected_season_id": selected_season_id,
            "columns": IMPORT_COLUMNS,
            "result": None,
            "error": None,
        },
    )


@router.post("/import")
async def player_import_post(
    request: Request,
    team_id: int | None = None,
    season_id: int | None = None,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form = await request.form()
    context_team = db.get(Team, team_id) if team_id else None

    season_id_s = (form.get("season_id") or "").strip()
    selected_season_id = (
        int(season_id_s) if season_id_s else (season_id or (_active_season_id(db) if team_id else None))
    )

    import_source = (form.get("import_source") or "").strip()
    error: str | None = None
    result: ImportResult | None = None

    all_teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    def _render(status: int = 200):
        return render(
            request,
            "players/import.html",
            {
                "user": user,
                "context_team": context_team,
                "all_teams": all_teams,
                "seasons": seasons,
                "selected_season_id": selected_season_id,
                "columns": IMPORT_COLUMNS,
                "result": result,
                "error": error,
            },
            status_code=status,
        )

    if import_source == "paste":
        rows_json = (form.get("rows_json") or "").strip()
        try:
            rows = json.loads(rows_json)
            if not isinstance(rows, list):
                raise ValueError("expected list")
        except (json.JSONDecodeError, ValueError):
            error = rt(request, "errors.invalid_data")
            return _render(400)
        result = process_rows(rows, context_team_id=team_id, db=db, context_season_id=selected_season_id)

    elif import_source == "file":
        upload = form.get("import_file")
        if upload is None or not upload.filename:
            error = rt(request, "errors.no_file")
            return _render(400)

        content = await upload.read()
        if len(content) > MAX_UPLOAD_BYTES:
            error = rt(request, "errors.file_too_large")
            return _render(400)

        filename = upload.filename.lower()
        try:
            if filename.endswith(".csv"):
                rows = parse_csv(io.BytesIO(content))
            elif filename.endswith(".xlsx"):
                rows = parse_xlsx(io.BytesIO(content))
            else:
                error = rt(request, "errors.unsupported_file_type")
                return _render(400)
        except ValueError as exc:
            error = f"Could not read the file: {exc}"
            return _render(400)

        result = process_rows(rows, context_team_id=team_id, db=db, context_season_id=selected_season_id)

    else:
        error = rt(request, "errors.invalid_submission")
        return _render(400)

    return _render()


# ---------------------------------------------------------------------------
# Search (must be before /{player_id} to avoid routing conflict)
# ---------------------------------------------------------------------------


@router.get("/search")
async def player_search(
    request: Request,
    q: str = "",
    exclude_event_id: int | None = None,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    """Return up to 20 active non-archived players matching `q` (name search).

    Excludes players who already have an Attendance row for `exclude_event_id`.
    Response: [{id, full_name, team_name}]
    """
    from models.attendance import Attendance  # noqa: PLC0415

    if len(q.strip()) < 2:
        return JSONResponse([])

    # Resolve season_id and existing attendees from the event
    season_id: int | None = None
    excluded_player_ids: set[int] = set()
    if exclude_event_id is not None:
        from models.event import Event as Ev  # noqa: PLC0415

        ev = db.get(Ev, exclude_event_id)
        if ev:
            season_id = ev.season_id
            excluded_player_ids = {
                row.player_id
                for row in db.query(Attendance.player_id).filter(Attendance.event_id == exclude_event_id).all()
            }

    term = f"%{q.strip()}%"
    query = db.query(Player).filter(
        Player.is_active.is_(True),
        Player.archived_at.is_(None),
        or_(Player.first_name.ilike(term), Player.last_name.ilike(term)),
    )
    # Apply exclusion at the DB level so the LIMIT applies to valid candidates only
    if excluded_player_ids:
        query = query.filter(~Player.id.in_(excluded_player_ids))
    players = query.limit(20).all()

    # Resolve team_name per player in the event's season
    results = []
    for p in players:
        team_name = None
        if season_id is not None:
            mem = (
                db.query(PlayerTeam)
                .filter(PlayerTeam.player_id == p.id, PlayerTeam.season_id == season_id)
                .order_by(PlayerTeam.priority.asc())
                .first()
            )
            if mem is not None:
                team = db.get(Team, mem.team_id)
                if team:
                    team_name = team.name
        results.append(
            {
                "id": p.id,
                "full_name": f"{p.first_name} {p.last_name}",
                "team_name": team_name,
            }
        )

    return JSONResponse(results)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{player_id}")
async def player_detail(
    player_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    history = get_player_attendance_history(db, player_id)
    _mems = sorted(player.team_memberships, key=lambda m: m.priority)
    sorted_memberships = sorted(_mems, key=lambda m: m.season.name if m.season else "", reverse=True)

    return render(
        request,
        "players/detail.html",
        {
            "user": user,
            "player": player,
            "history": history,
            "sorted_memberships": sorted_memberships,
        },
    )


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.get("/{player_id}/edit")
async def player_edit_get(
    player_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    active_season_id = _active_season_id(db)
    return render(
        request,
        "players/form.html",
        {
            "user": user,
            "player": player,
            "teams": teams,
            "users": users,
            "seasons": seasons,
            "active_season_id": active_season_id,
            "all_memberships": _all_memberships_dict(player),
            "error": None,
        },
    )


@router.post("/{player_id}/edit")
async def player_edit_post(
    player_id: int,
    request: Request,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    form = await request.form()
    first_name = (form.get("first_name") or "").strip()
    last_name = (form.get("last_name") or "").strip()
    email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip()
    user_id_s = (form.get("user_id") or "").strip()
    is_active = form.get("is_active") or ""

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    active_season_id = _active_season_id(db)

    if not first_name or not last_name:
        return render(
            request,
            "players/form.html",
            {
                "user": user,
                "player": player,
                "teams": teams,
                "users": users,
                "seasons": seasons,
                "active_season_id": active_season_id,
                "all_memberships": _all_memberships_dict(player),
                "error": rt(request, "errors.name_required"),
            },
            status_code=400,
        )

    parsed_user_id = int(user_id_s) if user_id_s else None
    if parsed_user_id is not None and parsed_user_id != player.user_id:
        conflict = db.query(Player).filter(Player.user_id == parsed_user_id).first()
        if conflict:
            return render(
                request,
                "players/form.html",
                {
                    "user": user,
                    "player": player,
                    "teams": teams,
                    "users": users,
                    "seasons": seasons,
                    "active_season_id": active_season_id,
                    "all_memberships": _all_memberships_dict(player),
                    "error": rt(request, "errors.user_already_linked"),
                },
                status_code=400,
            )

    player.first_name = first_name
    player.last_name = last_name
    player.email = email or None
    player.phone = phone or None
    player.user_id = parsed_user_id
    player.is_active = is_active in ("on", "true", "1", "yes")
    _apply_personal_fields(player, form)

    for s in seasons:
        _sync_memberships(db, player, _parse_team_memberships_for_season(form, s.id), season_id=s.id)
    _sync_phones(db, player, form)
    _sync_contact(db, player, form)

    db.add(player)
    db.commit()
    return RedirectResponse(f"/players/{player_id}", status_code=302)


# ---------------------------------------------------------------------------
# Archive / Unarchive
# ---------------------------------------------------------------------------


@router.post("/{player_id}/archive")
async def player_archive(
    player_id: int,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404)
    player.archived_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse("/players", status_code=302)


@router.post("/{player_id}/unarchive")
async def player_unarchive(
    player_id: int,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404)
    player.archived_at = None
    db.commit()
    return RedirectResponse("/players", status_code=302)
