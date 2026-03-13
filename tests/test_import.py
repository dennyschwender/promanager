"""Tests for services/import_service.py."""
import io
from datetime import date

import pytest

from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team
from services.import_service import parse_csv, parse_xlsx, process_rows

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def team(db):
    t = Team(name="Eagles")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def other_team(db):
    t = Team(name="Hawks")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ── process_rows ──────────────────────────────────────────────────────────────

def test_valid_rows_imported(db, team):
    rows = [{"first_name": "Alice", "last_name": "Smith"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert len(result.skipped) == 0
    player = db.query(Player).filter(Player.first_name == "Alice").first()
    assert player is not None
    assert player.is_active is True
    membership = db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id).first()
    assert membership is not None
    assert membership.team_id == team.id
    assert membership.role == "player"
    assert membership.membership_status == "active"
    assert membership.priority == 1
    assert membership.absent_by_default is False


def test_missing_first_name_skipped(db, team):
    rows = [{"first_name": "", "last_name": "Smith"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "missing required field"


def test_missing_last_name_skipped(db, team):
    rows = [{"first_name": "Alice", "last_name": "  "}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "missing required field"


def test_duplicate_by_email_skipped(db, team):
    existing = Player(first_name="Bob", last_name="Old", email="bob@test.com", is_active=True)
    db.add(existing)
    db.commit()
    rows = [{"first_name": "Bob", "last_name": "New", "email": "bob@test.com"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "duplicate"


def test_duplicate_by_name_skipped(db, team):
    existing = Player(first_name="Carol", last_name="Jones", is_active=True)
    db.add(existing)
    db.commit()
    rows = [{"first_name": "Carol", "last_name": "Jones"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "duplicate"


def test_duplicate_within_batch_skipped(db, team):
    rows = [
        {"first_name": "Dan", "last_name": "X", "email": "dan@test.com"},
        {"first_name": "Dan", "last_name": "Y", "email": "dan@test.com"},
    ]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert result.skipped[0]["reason"] == "duplicate (in batch)"


def test_unknown_team_falls_back_to_context(db, team):
    rows = [{"first_name": "Eve", "last_name": "X", "team": "Nonexistent"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert any("team not found" in s["reason"] for s in result.skipped)
    membership = db.query(PlayerTeam).join(Player).filter(Player.first_name == "Eve").first()
    assert membership.team_id == team.id


def test_blank_team_column_uses_context(db, team):
    rows = [{"first_name": "Frank", "last_name": "X", "team": ""}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert len(result.skipped) == 0


def test_named_team_column_resolved(db, team, other_team):
    rows = [{"first_name": "Grace", "last_name": "X", "team": "hawks"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    membership = db.query(PlayerTeam).join(Player).filter(Player.first_name == "Grace").first()
    assert membership.team_id == other_team.id


def test_unknown_columns_ignored(db, team):
    rows = [{"first_name": "Hank", "last_name": "X", "favourite_colour": "blue"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1


def test_invalid_date_of_birth_skipped(db, team):
    rows = [{"first_name": "Iris", "last_name": "X", "date_of_birth": "not-a-date"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "invalid date_of_birth"


def test_valid_date_formats_accepted(db, team):
    rows = [
        {"first_name": "J1", "last_name": "X", "date_of_birth": "2000-06-15"},
        {"first_name": "J2", "last_name": "X", "date_of_birth": "15/06/2000"},
        {"first_name": "J3", "last_name": "X", "date_of_birth": "15.06.2000"},
    ]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 3
    players = db.query(Player).filter(Player.last_name == "X").all()
    assert len(players) == 3
    for p in players:
        if p.first_name.startswith("J"):
            assert p.date_of_birth == date(2000, 6, 15)


# ── parse_csv ─────────────────────────────────────────────────────────────────

def test_parse_csv_basic():
    content = b"first_name,last_name,email\nAlice,Smith,alice@test.com\n"
    rows = parse_csv(io.BytesIO(content))
    assert len(rows) == 1
    assert rows[0]["first_name"] == "Alice"
    assert rows[0]["email"] == "alice@test.com"


def test_parse_csv_unknown_columns_passed_through():
    content = b"first_name,last_name,foo\nAlice,Smith,bar\n"
    rows = parse_csv(io.BytesIO(content))
    assert rows[0]["foo"] == "bar"


def test_parse_csv_case_insensitive_headers():
    content = b"First_Name,Last_Name\nAlice,Smith\n"
    rows = parse_csv(io.BytesIO(content))
    assert rows[0]["first_name"] == "Alice"


# ── parse_xlsx ────────────────────────────────────────────────────────────────

def test_parse_xlsx_basic():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["first_name", "last_name", "email"])
    ws.append(["Bob", "Jones", "bob@test.com"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    rows = parse_xlsx(buf)
    assert len(rows) == 1
    assert rows[0]["first_name"] == "Bob"
    assert rows[0]["email"] == "bob@test.com"


def test_parse_xlsx_case_insensitive_headers():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["First_Name", "Last_Name"])
    ws.append(["Bob", "Jones"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    rows = parse_xlsx(buf)
    assert rows[0]["first_name"] == "Bob"


def test_parse_xlsx_corrupt_file_raises_value_error():
    corrupt = io.BytesIO(b"not an xlsx file at all")
    with pytest.raises(ValueError, match="Cannot read XLSX file"):
        parse_xlsx(corrupt)
