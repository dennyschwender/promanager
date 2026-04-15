# Attendance Copy-to-Text & Telegram Format Improvements

**Date:** 2026-04-15

## Context

Coaches need to share attendance lists outside ProManager — e.g. pasting into WhatsApp group chats. The Telegram bot already generates a well-structured attendance summary for coaches/admins, but two issues exist: position groups lack counts, and externals appear in a separate section at the bottom rather than being integrated into the relevant status group. This spec covers:

1. A web copy-to-clipboard button on the event detail page that generates the same plain-text format as the Telegram summary, respecting the page's existing position-grouping toggle.
2. Two fixes to the existing Telegram attendance format: count per position group and externals placed inside their matching status section.

## Text Format

Both the web and Telegram output share the same structure (Telegram adds Markdown bold/italic markers):

```
Event: <title>
Date: <date>
Time: <start> - <end>
Location: <location>

Attendance: ✓ 21 | ✗ 8 | ? 0

✓ Present
Goalies (2)
  Alex David
  Andrin Bechtiger
Defenders (4)
  ...
👤 Mauro Ochsner          ← external, integrated here

✗ Absent
Defenders (3)
  ...
```

**Rules:**
- Position groups show `Label (N)` where N is the count of players in that group.
- Externals appear at the end of their matching status section (after all position sub-groups), each prefixed with `👤`. No separate "Externals" block.
- When `grouped=false`: position headers are omitted; each status section lists players (then externals) in a flat list.
- Only statuses that have at least one player or external are included.
- Follows the same player-resolution logic as the current Telegram handler: all players assigned to the event's team+season are shown, grouped by their attendance status (including `unknown`).

## Architecture

### New shared service: `services/event_text_service.py`

Single public function:

```python
def format_attendance_text(
    db: Session,
    event: Event,
    locale: str,
    grouped: bool = True,
    markdown: bool = False,
) -> str
```

- Loads `PlayerTeam` rows for the event's `(team_id, season_id)` to get positions.
- Loads `Attendance` and `EventExternal` rows for the event.
- Builds the header block (title, date, time, location, meeting info, counts line).
- Builds the body: status → position → players, with externals appended per status.
- Applies Markdown bold/italic only when `markdown=True`.

### Modified: `bot/handlers.py`

Replace the inline formatting block (lines ~570–626) with:

```python
from services.event_text_service import format_attendance_text

body = format_attendance_text(db, event, locale, grouped=True, markdown=True)
text += "\n" + body
```

The two fixes (position counts + externals placement) land here automatically via the shared service.

### New endpoint: `routes/events.py`

```
GET /events/{event_id}/attendance-text?grouped=1
```

- Auth: `require_login` (same guard as the event detail page).
- Calls `format_attendance_text(db, event, locale, grouped=grouped, markdown=False)`.
- Returns `Response(content=text, media_type="text/plain")`.
- 404 if event not found; 403 if user has no access to the team.

### Modified: `templates/events/detail.html`

A copy button added near the attendance counts header (visible to all authenticated users viewing the event). On click:

1. Read `localStorage.getItem("att_pos_grouping")` to determine `grouped`.
2. `fetch(`/events/${eventId}/attendance-text?grouped=${grouped}`)`.
3. `navigator.clipboard.writeText(text)`.
4. Button label briefly changes to a "Copied!" confirmation, then reverts.

### Locales (`en.json`, `it.json`, `fr.json`, `de.json`)

New key: `events.copy_attendance` — label for the copy button (e.g. "Copy attendance").

## Files to Change

| File | Change |
|------|--------|
| `services/event_text_service.py` | **New** — shared formatter |
| `bot/handlers.py` | Replace inline block with service call |
| `routes/events.py` | Add `GET /events/{id}/attendance-text` endpoint |
| `templates/events/detail.html` | Add copy button + JS |
| `locales/en.json`, `it.json`, `fr.json`, `de.json` | Add `events.copy_attendance` key |

## Verification

1. **Telegram**: Open an event as coach/admin in the Telegram bot. Verify:
   - Position groups show counts: `Goalies (2)`, `Defenders (4)`.
   - Externals appear within the correct status section (e.g. a present external is under `✓ Present`), not in a trailing "Externals" block.
2. **Web endpoint**: `curl -b <session_cookie> /events/16/attendance-text?grouped=1` returns readable plain text with the expected structure.
3. **Web button (grouped)**: Enable position grouping toggle on the event detail page. Click copy. Paste into a text editor — position headers with counts should appear.
4. **Web button (flat)**: Disable position grouping toggle. Click copy. Paste — flat list per status, no position headers.
5. **Externals edge cases**: Event with no externals — no `👤` lines. Event with absent external — external appears under `✗ Absent`.
6. **Run tests**: `pytest -v` passes. `ruff check .` passes.
