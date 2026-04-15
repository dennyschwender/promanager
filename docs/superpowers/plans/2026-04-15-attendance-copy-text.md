# Attendance Copy-to-Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clipboard copy button to the event detail page that exports attendance as plain text (matching the Telegram format), and fix the Telegram coach/admin view to show position counts and integrate externals into their status sections.

**Architecture:** A new `services/event_text_service.py` provides two functions — `format_attendance_body()` used by the Telegram handler and `format_attendance_text()` used by a new `GET /events/{id}/attendance-text` endpoint. The copy button in the template reads the page's existing `att_pos_grouping` localStorage key, fetches the endpoint, and writes to clipboard.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Jinja2, vanilla JS, python-telegram-bot (existing), `app.i18n.t()` for translations.

---

## File Map

| File | Action |
|------|--------|
| `services/event_text_service.py` | **Create** — shared attendance text formatter |
| `tests/test_event_text_service.py` | **Create** — unit tests for the service |
| `bot/handlers.py` | **Modify** — replace inline body block (lines 557–626) with service call; rename `_bot_position` → `_position` |
| `routes/events.py` | **Modify** — add `GET /events/{event_id}/attendance-text` endpoint |
| `tests/test_events.py` | **Modify** — add tests for the new endpoint |
| `templates/events/detail.html` | **Modify** — add copy button + JS near the attendance header |
| `locales/en.json` | **Modify** — add `events_detail.copy_attendance` key |
| `locales/it.json` | **Modify** — add `events_detail.copy_attendance` key |
| `locales/fr.json` | **Modify** — add `events_detail.copy_attendance` key |
| `locales/de.json` | **Modify** — add `events_detail.copy_attendance` key |

---

## Task 1: Create `services/event_text_service.py`

**Files:**
- Create: `services/event_text_service.py`
- Create: `tests/test_event_text_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_event_text_service.py`:

```python
"""Tests for services/event_text_service.py."""

from datetime import date, time

import pytest

from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from services.event_text_service import format_attendance_body, format_attendance_text


# ---------------------------------------------------------------------------
# format_attendance_body
# ---------------------------------------------------------------------------


def _make_player(id_, first, last, position=None):
    p = Player(id=id_, first_name=first, last_name=last)
    p._position = position
    return p


def _make_att(player_id, status, note=None):
    return Attendance(player_id=player_id, status=status, note=note)


def _make_ext(id_, first, last, status, note=None):
    return EventExternal(id=id_, first_name=first, last_name=last, status=status, note=note)


def test_body_position_counts_grouped():
    players = [
        _make_player(1, "Alice", "A", "goalie"),
        _make_player(2, "Bob", "B", "goalie"),
        _make_player(3, "Carl", "C", "defender"),
    ]
    att = {
        1: _make_att(1, "present"),
        2: _make_att(2, "present"),
        3: _make_att(3, "present"),
    }
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "Goalies (2)" in result
    assert "Defenders (1)" in result
    assert "Alice A" in result
    assert "Carl C" in result


def test_body_externals_integrated_by_status():
    players = [_make_player(1, "Dave", "D", "forward")]
    att = {1: _make_att(1, "present")}
    exts = [
        _make_ext(10, "Eve", "E", "present"),
        _make_ext(11, "Frank", "F", "absent"),
    ]
    result = format_attendance_body(players, att, exts, "en", grouped=True, markdown=False)
    # Eve (present external) should appear BEFORE the absent section
    assert "👤 Eve E" in result
    assert "👤 Frank F" in result
    present_idx = result.index("✓ Present")
    absent_idx = result.index("✗ Absent")
    eve_idx = result.index("👤 Eve E")
    frank_idx = result.index("👤 Frank F")
    assert present_idx < eve_idx < absent_idx
    assert absent_idx < frank_idx


def test_body_no_externals_block_header():
    """No separate 'Externals' heading should appear."""
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present")}
    exts = [_make_ext(10, "Eve", "E", "present")]
    result = format_attendance_body(players, att, exts, "en", grouped=True, markdown=False)
    assert "Externals" not in result


def test_body_flat_list_no_position_headers():
    players = [
        _make_player(1, "Alice", "A", "goalie"),
        _make_player(2, "Bob", "B", "defender"),
    ]
    att = {
        1: _make_att(1, "present"),
        2: _make_att(2, "present"),
    }
    result = format_attendance_body(players, att, [], "en", grouped=False, markdown=False)
    assert "Goalies" not in result
    assert "Defenders" not in result
    assert "Alice A" in result
    assert "Bob B" in result


def test_body_markdown_bold_italic():
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=True)
    assert "*" in result   # bold status header
    assert "_Goalies" in result  # italic position label


def test_body_skips_empty_statuses():
    players = [_make_player(1, "Alice", "A")]
    att = {1: _make_att(1, "present")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "✗ Absent" not in result
    assert "? Unknown" not in result


def test_body_player_note_included():
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present", note="knee injury")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "knee injury" in result


# ---------------------------------------------------------------------------
# format_attendance_text  (integration — needs a real DB session)
# ---------------------------------------------------------------------------


def test_format_attendance_text_header(db):
    team = Team(name="T1")
    season = Season(name="S1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="NLB Final",
        event_type="match",
        event_date=date(2026, 4, 16),
        event_time=time(19, 30),
        event_end_time=time(22, 0),
        location="SAM Bellinzona",
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Alex", last_name="Smith")
    db.add(player)
    db.commit()

    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="goalie"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    result = format_attendance_text(db, event, "en", grouped=True, markdown=False)

    assert "NLB Final" in result
    assert "2026-04-16" in result
    assert "19:30" in result
    assert "22:00" in result
    assert "SAM Bellinzona" in result
    assert "Attendance:" in result
    assert "Alex Smith" in result
    assert "Goalies (1)" in result


def test_format_attendance_text_external_in_status(db):
    team = Team(name="T2")
    season = Season(name="S2", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Training",
        event_type="training",
        event_date=date(2026, 4, 20),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    ext = EventExternal(event_id=event.id, first_name="Mauro", last_name="Ochsner", status="present")
    db.add(ext)
    db.commit()

    result = format_attendance_text(db, event, "en", grouped=True, markdown=False)
    assert "👤 Mauro Ochsner" in result
    assert "Externals" not in result  # no separate block
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_event_text_service.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `event_text_service` does not exist yet.

- [ ] **Step 3: Implement `services/event_text_service.py`**

Create `services/event_text_service.py`:

```python
"""services/event_text_service.py — Shared attendance text formatter.

Used by both the Telegram bot handler (markdown=True) and the web
attendance-text endpoint (markdown=False).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.i18n import DEFAULT_LOCALE
from app.i18n import t as _t
from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam

_STATUS_ORDER = ["present", "absent", "maybe", "unknown"]
_POS_ORDER: list[str | None] = ["goalie", "defender", "center", "forward", None]
_STATUS_ICON = {"present": "✓", "absent": "✗", "unknown": "?", "maybe": "~"}


def format_attendance_body(
    players: list,
    att_by_player: dict,
    ext_rows: list,
    locale: str,
    grouped: bool = True,
    markdown: bool = False,
) -> str:
    """Render the player+external listing section of the attendance text.

    Players must have a ``_position`` attribute (str | None) set by the caller.
    Externals are integrated into their matching status section, not appended
    at the end. Position sub-headers include a player count when grouped=True.
    """
    def _bold(s: str) -> str:
        return f"*{s}*" if markdown else s

    def _italic(s: str) -> str:
        return f"_{s}_" if markdown else s

    status_header = {
        "present": _bold(_t("telegram.status_present", locale)),
        "absent": _bold(_t("telegram.status_absent", locale)),
        "maybe": _bold(_t("telegram.status_maybe", locale)),
        "unknown": _bold(_t("telegram.status_unknown", locale)),
    }
    pos_label: dict[str | None, str] = {
        "goalie": _t("telegram.pos_goalie", locale),
        "defender": _t("telegram.pos_defender", locale),
        "center": _t("telegram.pos_center", locale),
        "forward": _t("telegram.pos_forward", locale),
        None: _t("telegram.pos_other", locale),
    }

    # Group externals by status
    ext_by_status: dict[str, list] = {s: [] for s in _STATUS_ORDER}
    for ext in ext_rows:
        s = ext.status if ext.status in ext_by_status else "unknown"
        ext_by_status[s].append(ext)

    # Group players by status → position
    status_groups: dict[str, dict[str | None, list]] = {
        s: {pos: [] for pos in _POS_ORDER} for s in _STATUS_ORDER
    }
    for p in players:
        att = att_by_player.get(p.id)
        s = (att.status if att else "unknown") or "unknown"
        if s not in status_groups:
            s = "unknown"
        pos = getattr(p, "_position", None)
        if pos not in _POS_ORDER[:-1]:
            pos = None
        status_groups[s][pos].append(p)

    lines: list[str] = []
    for s in _STATUS_ORDER:
        pos_group = status_groups[s]
        exts = ext_by_status[s]
        if not any(pos_group.values()) and not exts:
            continue
        lines.append(f"\n{status_header[s]}")
        if grouped:
            for pos in _POS_ORDER:
                group = pos_group[pos]
                if not group:
                    continue
                label = f"{pos_label[pos]} ({len(group)})"
                lines.append(_italic(label))
                for p in group:
                    att = att_by_player.get(p.id)
                    line = f"  {p.full_name}"
                    if att and att.note:
                        line += f" — {att.note}"
                    lines.append(line)
        else:
            # Flat list — merge all positions and sort by name
            all_players = [p for pos in _POS_ORDER for p in pos_group[pos]]
            all_players.sort(key=lambda p: p.full_name)
            for p in all_players:
                att = att_by_player.get(p.id)
                line = f"  {p.full_name}"
                if att and att.note:
                    line += f" — {att.note}"
                lines.append(line)
        # Externals for this status, integrated here
        for ext in exts:
            ext_line = f"👤 {ext.full_name}"
            if ext.note:
                ext_line += f" — {ext.note}"
            lines.append(ext_line)

    return "\n".join(lines)


def format_attendance_text(
    db: Session,
    event: Event,
    locale: str = DEFAULT_LOCALE,
    grouped: bool = True,
    markdown: bool = False,
) -> str:
    """Render a complete shareable attendance summary for the given event.

    Includes the event header block (title, date, time, location, counts)
    followed by the full player+external listing.
    """
    def _bold(s: str) -> str:
        return f"*{s}*" if markdown else s

    # Header
    if event.event_type in ("training", "match"):
        event_type_str = _t(f"telegram.event_type_{event.event_type}", locale)
    else:
        event_type_str = _t("telegram.event_type_other", locale)

    lines: list[str] = [_bold(f"{event_type_str}: {event.title}")]
    lines.append(f"{_t('telegram.date_label', locale)}: {event.event_date}")

    if event.event_time:
        time_str = str(event.event_time)[:5]
        if event.event_end_time:
            time_str += f" - {str(event.event_end_time)[:5]}"
        lines.append(f"{_t('telegram.time_label', locale)}: {time_str}")

    if event.location:
        lines.append(f"{_t('telegram.location_label', locale)}: {event.location}")

    if event.meeting_time:
        meet = str(event.meeting_time)[:5]
        if event.meeting_location:
            meet += f" @ {event.meeting_location}"
        lines.append(f"{_t('telegram.meeting_label', locale)}: {meet}")

    # Load attendance data
    atts = db.query(Attendance).filter(Attendance.event_id == event.id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    ext_rows = (
        db.query(EventExternal)
        .filter(EventExternal.event_id == event.id)
        .order_by(EventExternal.created_at)
        .all()
    )

    # Counts line
    counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    for ext in ext_rows:
        counts[ext.status] = counts.get(ext.status, 0) + 1
    lines.append(
        f"\n{_t('telegram.attendance_label', locale)}: "
        f"✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
    )

    # Load players for this event's team+season
    if event.team_id and event.season_id:
        pt_rows = (
            db.query(PlayerTeam)
            .filter(
                PlayerTeam.team_id == event.team_id,
                PlayerTeam.season_id == event.season_id,
            )
            .all()
        )
        player_ids = {pt.player_id: pt.position for pt in pt_rows}
        players_q = (
            db.query(Player)
            .filter(Player.id.in_(player_ids.keys()), Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
        for p in players_q:
            p._position = player_ids.get(p.id)  # type: ignore[attr-defined]
    else:
        players_q = (
            db.query(Player)
            .filter(Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
        for p in players_q:
            p._position = None  # type: ignore[attr-defined]

    body = format_attendance_body(
        players_q, att_by_player, ext_rows, locale, grouped=grouped, markdown=markdown
    )
    lines.append(body)

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_event_text_service.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/event_text_service.py tests/test_event_text_service.py
git commit -m "feat: add event_text_service with format_attendance_body/text"
```

---

## Task 2: Update `bot/handlers.py`

**Files:**
- Modify: `bot/handlers.py:557-626`

This task has two changes:
1. Rename `_bot_position` → `_position` (lines 557–568)
2. Replace the inline body-building block (lines 570–626) with a call to `format_attendance_body`

- [ ] **Step 1: Rename `_bot_position` to `_position` in the player-loading section**

In `bot/handlers.py`, find these two lines (around 557–568):

```python
            for p in players_q:
                p._bot_position = player_ids.get(p.id)  # type: ignore[attr-defined]
            players = players_q
        else:
            players = (
                db.query(Player)
                .filter(Player.archived_at.is_(None))
                .order_by(Player.first_name, Player.last_name)
                .all()
            )
            for p in players:
                p._bot_position = None  # type: ignore[attr-defined]
```

Replace with:

```python
            for p in players_q:
                p._position = player_ids.get(p.id)  # type: ignore[attr-defined]
            players = players_q
        else:
            players = (
                db.query(Player)
                .filter(Player.archived_at.is_(None))
                .order_by(Player.first_name, Player.last_name)
                .all()
            )
            for p in players:
                p._position = None  # type: ignore[attr-defined]
```

- [ ] **Step 2: Replace the inline body block with a service call**

Find the block starting at `# Group by status → position → name` (around line 570) through the line `text += "\n" + "\n".join(pos_lines)` (around line 626):

```python
        # Group by status → position → name
        _STATUS_ORDER = ["present", "absent", "maybe", "unknown"]
        _STATUS_HEADER = {
            "present": f"*{t('telegram.status_present', locale)}*",
            "absent": f"*{t('telegram.status_absent', locale)}*",
            "maybe": f"*{t('telegram.status_maybe', locale)}*",
            "unknown": f"*{t('telegram.status_unknown', locale)}*",
        }
        _POS_ORDER = ["goalie", "defender", "center", "forward", None]
        _POS_LABEL = {
            "goalie": t("telegram.pos_goalie", locale),
            "defender": t("telegram.pos_defender", locale),
            "center": t("telegram.pos_center", locale),
            "forward": t("telegram.pos_forward", locale),
            None: t("telegram.pos_other", locale),
        }

        # Build status → position → [Player] structure
        status_groups: dict[str, dict[str | None, list[Player]]] = {
            s: {pos: [] for pos in _POS_ORDER} for s in _STATUS_ORDER
        }
        for p in players:
            att = att_by_player.get(p.id)
            s = att.status if att else "unknown"
            if s not in status_groups:
                s = "unknown"
            pos = getattr(p, "_bot_position", None)
            if pos not in _POS_ORDER[:-1]:
                pos = None
            status_groups[s][pos].append(p)

        pos_lines: list[str] = []
        for s in _STATUS_ORDER:
            pos_group = status_groups[s]
            if not any(pos_group.values()):
                continue
            pos_lines.append(f"\n{_STATUS_HEADER[s]}")
            for pos in _POS_ORDER:
                group = pos_group[pos]
                if not group:
                    continue
                pos_lines.append(f"_{_POS_LABEL[pos]}_")
                for p in group:
                    att = att_by_player.get(p.id)
                    line = f"  {p.full_name}"
                    if att and att.note:
                        line += f" — {att.note}"
                    pos_lines.append(line)
        if ext_rows:
            pos_lines.append(f"\n*{t('telegram.externals_header', locale)}*")
            for ext in ext_rows:
                icon = STATUS_ICON.get(ext.status, "?")
                ext_line = f"{icon} 👤 _{ext.full_name}_"
                if ext.note:
                    ext_line += f" — {ext.note}"
                pos_lines.append(ext_line)
        text += "\n" + "\n".join(pos_lines)
```

Replace with:

```python
        from services.event_text_service import format_attendance_body
        text += "\n" + format_attendance_body(
            players, att_by_player, ext_rows, locale, grouped=True, markdown=True
        )
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers.py
git commit -m "fix(telegram): use shared formatter — adds position counts and integrates externals by status"
```

---

## Task 3: Add web endpoint `GET /events/{event_id}/attendance-text`

**Files:**
- Modify: `routes/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_events.py`:

```python
# ---------------------------------------------------------------------------
# Attendance text endpoint
# ---------------------------------------------------------------------------


def test_attendance_text_returns_plain_text(admin_client, db):
    from datetime import date, time as dtime

    from models.attendance import Attendance
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    team = Team(name="TextTeam")
    season = Season(name="S1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Copy Test Match",
        event_type="match",
        event_date=date(2026, 4, 16),
        event_time=dtime(19, 30),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Zeno", last_name="Boscolo")
    db.add(player)
    db.commit()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="forward"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.get(f"/events/{event.id}/attendance-text?grouped=1")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "Copy Test Match" in body
    assert "Zeno Boscolo" in body
    assert "Forwards (1)" in body


def test_attendance_text_flat(admin_client, db):
    from datetime import date

    from models.attendance import Attendance
    from models.player import Player
    from models.player_team import PlayerTeam
    from models.season import Season
    from models.team import Team

    team = Team(name="FlatTeam")
    season = Season(name="S2", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Flat Test",
        event_type="training",
        event_date=date(2026, 4, 17),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Anna", last_name="Z")
    db.add(player)
    db.commit()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="defender"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.get(f"/events/{event.id}/attendance-text?grouped=0")
    assert resp.status_code == 200
    body = resp.text
    assert "Anna Z" in body
    assert "Defenders" not in body  # no position headers in flat mode


def test_attendance_text_404(admin_client):
    resp = admin_client.get("/events/99999/attendance-text?grouped=1")
    assert resp.status_code == 404


def test_attendance_text_requires_login(client):
    resp = client.get("/events/1/attendance-text?grouped=1", follow_redirects=False)
    assert resp.status_code == 302
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_events.py::test_attendance_text_returns_plain_text tests/test_events.py::test_attendance_text_flat tests/test_events.py::test_attendance_text_404 tests/test_events.py::test_attendance_text_requires_login -v
```

Expected: 404 response for the endpoint (route does not exist yet).

- [ ] **Step 3: Add the endpoint to `routes/events.py`**

Add this import at the top of `routes/events.py` (with the other service imports):

```python
from services.event_text_service import format_attendance_text
```

Then add this endpoint after the existing `event_detail` handler (after line ~579, i.e. before the edit handler):

```python
@router.get("/{event_id}/attendance-text")
async def event_attendance_text(
    event_id: int,
    request: Request,
    grouped: int = 1,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response

    from app.i18n import DEFAULT_LOCALE

    event = db.get(Event, event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    text = format_attendance_text(db, event, locale, grouped=bool(grouped), markdown=False)
    return Response(content=text, media_type="text/plain; charset=utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_events.py::test_attendance_text_returns_plain_text tests/test_events.py::test_attendance_text_flat tests/test_events.py::test_attendance_text_404 tests/test_events.py::test_attendance_text_requires_login -v
```

Expected: all four pass.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add routes/events.py tests/test_events.py
git commit -m "feat: add GET /events/{id}/attendance-text endpoint"
```

---

## Task 4: Copy button in template + locales

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/it.json`
- Modify: `locales/fr.json`
- Modify: `locales/de.json`
- Modify: `templates/events/detail.html`

- [ ] **Step 1: Add i18n keys to all four locale files**

In `locales/en.json`, find the `"events_detail"` section. Add `"copy_attendance"` (keep alphabetical or append before the closing brace):

Search for `"group_by_pos"` in the `events_detail` section and add the new key nearby:

```json
"copy_attendance": "Copy attendance",
```

In `locales/it.json`, add:

```json
"copy_attendance": "Copia presenze",
```

In `locales/fr.json`, add:

```json
"copy_attendance": "Copier les présences",
```

In `locales/de.json`, add:

```json
"copy_attendance": "Anwesenheit kopieren",
```

To find where to insert, look for `"group_by_pos"` in each locale's `events_detail` section — add the new key in the same object.

- [ ] **Step 2: Add the copy button to `templates/events/detail.html`**

Find this block (around line 114–117):

```html
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem;">
  <h3 style="margin:0;">{{ t('events.attendance_summary') }}</h3>
  <button type="button" id="pos-group-toggle" class="btn btn-sm btn-outline">{{ t('events_detail.group_by_pos') }}</button>
</div>
```

Replace with:

```html
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem;">
  <h3 style="margin:0;">{{ t('events.attendance_summary') }}</h3>
  <div style="display:flex;gap:.5rem;">
    <button type="button" id="copy-att-btn" class="btn btn-sm btn-outline">{{ t('events_detail.copy_attendance') }}</button>
    <button type="button" id="pos-group-toggle" class="btn btn-sm btn-outline">{{ t('events_detail.group_by_pos') }}</button>
  </div>
</div>
```

- [ ] **Step 3: Add copy button JS to `templates/events/detail.html`**

Find the closing `</script>` of the existing attendance script block (the one that contains `applyGrouping`). It ends around line 426 or after the `TOGGLE_BTN.addEventListener` block.

Just before the `</script>` tag of that block, insert:

```javascript
  // Copy attendance button
  (function () {
    var copyBtn = document.getElementById('copy-att-btn');
    if (!copyBtn) return;
    copyBtn.addEventListener('click', function () {
      var orig = copyBtn.textContent;
      var grouped;
      try { grouped = localStorage.getItem('att_pos_grouping'); } catch(e) { grouped = null; }
      var groupedParam = (grouped === null || grouped === '1') ? '1' : '0';
      fetch('/events/' + EVENT_ID + '/attendance-text?grouped=' + groupedParam)
        .then(function (r) { return r.text(); })
        .then(function (text) {
          navigator.clipboard.writeText(text).then(function () {
            copyBtn.textContent = '✓ Copied!';
            copyBtn.disabled = true;
            setTimeout(function () {
              copyBtn.textContent = orig;
              copyBtn.disabled = false;
            }, 2000);
          });
        })
        .catch(function () {
          copyBtn.textContent = 'Error';
          setTimeout(function () { copyBtn.textContent = orig; }, 2000);
        });
    });
  })();
```

Note: `EVENT_ID` is already defined at the top of the script block (`var EVENT_ID = {{ event.id }};`).

- [ ] **Step 4: Run full test suite**

```bash
pytest -v && ruff check .
```

Expected: all tests pass, no ruff errors.

- [ ] **Step 5: Commit**

```bash
git add locales/en.json locales/it.json locales/fr.json locales/de.json templates/events/detail.html
git commit -m "feat: add copy-attendance button to event detail page"
```

---

## Verification Checklist

After all tasks are complete, verify end-to-end:

1. **Telegram — position counts**: Open an event as coach in Telegram bot. Confirm position headers show counts: `Goalies (2)`, `Defenders (4)`.

2. **Telegram — externals placement**: Add an external (present). Confirm they appear under `✓ Present`, not in a trailing `Externals` block.

3. **Web endpoint grouped**: `curl -s -b 'session_user_id=<cookie>' 'http://localhost:7000/events/16/attendance-text?grouped=1'` — should return readable plain text with position headers and counts.

4. **Web endpoint flat**: Same but `grouped=0` — no position headers, just flat name lists per status.

5. **Copy button (grouped)**: On the event detail page, enable the position-grouping toggle (button turns primary/filled). Click "Copy attendance". Paste into a text editor — verify position headers with counts appear, externals are in the right section.

6. **Copy button (flat)**: Disable the toggle. Click "Copy attendance". Paste — no position headers.

7. **Copy button feedback**: Click the button. Confirm it briefly shows "✓ Copied!" then reverts.
