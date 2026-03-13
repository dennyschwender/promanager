"""services/import_service.py — Bulk player import logic."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team


@dataclass
class ImportResult:
    imported: list[Player] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {row, name, reason}


def _parse_date(value: str) -> date | None:
    """Return a date from YYYY-MM-DD, DD/MM/YYYY, or DD.MM.YYYY. Raise ValueError if invalid."""
    v = value.strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        pass
    for sep in ("/", "."):
        parts = v.split(sep)
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return date(year, month, day)
            except (ValueError, TypeError):
                pass
    raise ValueError(f"Cannot parse date: {v!r}")


def _normalise_headers(headers: list[str]) -> list[str]:
    return [h.strip().lower() for h in headers]


def parse_csv(stream: BinaryIO) -> list[dict]:
    """Parse a CSV stream; returns list of dicts with lower-cased header keys."""
    try:
        text = stream.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Cannot decode CSV file: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({k.strip().lower(): (v or "").strip() for k, v in row.items()})
    return rows


def parse_xlsx(stream: BinaryIO) -> list[dict]:
    """Parse an XLSX stream; returns list of dicts with lower-cased header keys.

    Raises ValueError if the stream is not a valid XLSX file.
    """
    import openpyxl
    try:
        wb = openpyxl.load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Cannot read XLSX file: {exc}") from exc
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = _normalise_headers([str(c) if c is not None else "" for c in next(rows_iter)])
    except StopIteration:
        return []
    result = []
    for row in rows_iter:
        result.append({
            headers[i]: str(cell).strip() if cell is not None else ""
            for i, cell in enumerate(row)
            if i < len(headers)
        })
    return result


def process_rows(
    rows: list[dict],
    context_team_id: int,
    db: Session,
) -> ImportResult:
    """Process import rows best-effort (per-row independent commits via savepoints)."""
    result = ImportResult()
    seen_keys: set[str] = set()

    all_teams = {t.name.lower(): t for t in db.query(Team).all()}
    context_team = db.get(Team, context_team_id)
    ctx_name = context_team.name if context_team else str(context_team_id)

    for idx, raw in enumerate(rows, start=1):
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        display_name = f"{first_name} {last_name}".strip() or f"row {idx}"

        def skip(reason: str) -> None:
            result.skipped.append({"row": idx, "name": display_name, "reason": reason})

        # 1. Required fields
        if not first_name or not last_name:
            skip("missing required field")
            continue

        # 2. Duplicate detection
        email = row.get("email", "").strip().lower()
        batch_key = email if email else f"{first_name.lower()}|{last_name.lower()}"
        if batch_key in seen_keys:
            skip("duplicate (in batch)")
            continue

        if email:
            existing = db.query(Player).filter(Player.email.ilike(email)).first()
        else:
            existing = db.query(Player).filter(
                Player.first_name.ilike(first_name),
                Player.last_name.ilike(last_name),
            ).first()

        if existing:
            skip("duplicate")
            continue

        # 3. Team resolution
        team_name = row.get("team", "").strip()
        resolved_team_id = context_team_id
        team_warning: str | None = None
        if team_name:
            matched = all_teams.get(team_name.lower())
            if matched:
                resolved_team_id = matched.id
            else:
                team_warning = f"team not found: {team_name}, assigned to {ctx_name}"

        # 4. Date parsing
        dob_raw = row.get("date_of_birth", "").strip()
        dob: date | None = None
        if dob_raw:
            try:
                dob = _parse_date(dob_raw)
            except ValueError:
                skip("invalid date_of_birth")
                continue

        # 5. Create player + membership within a savepoint
        try:
            sp = db.begin_nested()
            player = Player(
                first_name=first_name,
                last_name=last_name,
                email=row.get("email", "").strip() or None,
                phone=row.get("phone", "").strip() or None,
                sex=row.get("sex", "").strip() or None,
                date_of_birth=dob,
                street=row.get("street", "").strip() or None,
                postcode=row.get("postcode", "").strip() or None,
                city=row.get("city", "").strip() or None,
                is_active=True,
            )
            db.add(player)
            db.flush()
            db.add(PlayerTeam(
                player_id=player.id,
                team_id=resolved_team_id,
                priority=1,
                role="player",
                membership_status="active",
                absent_by_default=False,
            ))
            sp.commit()
        except SQLAlchemyError:
            sp.rollback()
            skip("db error")
            continue

        seen_keys.add(batch_key)
        result.imported.append(player)
        if team_warning:
            result.skipped.append({"row": idx, "name": display_name, "reason": team_warning})

    db.commit()
    return result
