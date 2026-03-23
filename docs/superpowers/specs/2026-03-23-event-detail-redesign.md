# Event Detail Page Redesign

**Date:** 2026-03-23
**Status:** Approved
**Primary user:** Coach / Admin managing an event

---

## Goal

Replace the current flat event detail page (info block → action buttons → static attendance summary) with a coach-focused layout where attendance management is the primary interaction. The page should allow a coach to read attendance status at a glance and update individual player statuses without leaving the page.

---

## Layout

### 1. Header

- Event title (`<h2>`)
- Inline badges: event type, presence type, recurring indicator
- Compact info strip (single line, not a `<dl>`):
  `📅 2026-03-28 · 20:45 → 22:00 · 📍 Arti e Mestieri · Meeting: 20:15`
- Only show fields that have values (date always shown; others hidden if empty)

### 2. Action Bar

Three groups in one row:

| Left | Center | Right |
|------|--------|-------|
| `← Back` (outline, sm) | `Edit` (outline) — admin/coach only | `⋯` dropdown |

The `⋯` dropdown contains (admin/coach only):
- Notify players
- Send reminders
- Divider
- Delete (danger color)

`Edit` stays visible as a primary secondary action since coaches use it regularly. Everything else moves to the dropdown to keep focus on attendance.

### 3. Attendance Section

Only rendered when `event.presence_type != "no_registration"`.

**Column layout** (CSS flex/grid, responsive):
One card per status bucket: **Present · Absent · Maybe · Unknown**

Rules:
- Each column shows a header badge with count: e.g. `Present (8)`
- Empty columns are hidden entirely, including Unknown when count is 0
- Player names listed vertically inside each column
- Each player name is a clickable element (button styled as text link)

**Player popover** (opens on click):
- Triggered by clicking a player name
- Shows player's name as popover title
- Four status buttons in a row: Present / Absent / Maybe / Unknown — current status visually highlighted
- Optional note textarea (pre-filled with existing note if any)
- Save button — submits via `fetch()` AJAX, closes popover, moves player to new column without page reload
- Close/cancel button

Only one popover open at a time. Clicking outside closes the active popover.

---

## Backend Changes

### New JSON endpoint for AJAX attendance updates

Add `Accept: application/json` branch (or a separate route) to the existing `POST /attendance/{event_id}/{player_id}`:

```
POST /attendance/{event_id}/{player_id}
Content-Type: application/x-www-form-urlencoded

status=present&note=...&csrf_token=...
```

When the request has `X-Requested-With: fetch` header (or `Accept: application/json`), return:

```json
{ "ok": true, "status": "present", "note": "..." }
```

instead of redirecting. Authorization logic stays identical.

### Event detail route (`/events/{event_id}`)

No structural changes needed. The `summary` dict already groups players by bucket. The template change is purely frontend.

---

## Frontend Implementation

### Template: `templates/events/detail.html`

- Rewrite layout per design above
- Attendance columns rendered server-side (Jinja2); JavaScript only handles popover open/close and AJAX submit
- No external JS libraries needed — vanilla JS

### JavaScript (inline in template)

Small, self-contained script (~80 lines):
- `openPopover(playerId, currentStatus, currentNote)` — renders and positions popover
- `closePopover()` — removes active popover
- `submitStatus(eventId, playerId, status, note)` — fetch POST, on success calls `movePlayer(playerId, newStatus)`
- `movePlayer(playerId, newStatus)` — removes player element from current column, appends to target column, updates column counts, hides column if now empty

CSRF token read from `<meta name="csrf-token">` (already present in the template).

---

## Out of Scope

- Drag-and-drop between columns (popover is sufficient and more accessible)
- Bulk status changes (not needed for this workflow)
- Attendance history per player (exists on player detail page)
- Modifying the separate `/attendance/{event_id}` page (keep as-is for player self-reporting)

---

## Testing

- Existing `test_attendance.py` tests cover the POST endpoint — they remain valid
- Manually verify: open popover → change status → player moves column → count updates → column hides when emptied
- Verify empty-column hiding for all four buckets
- Verify CSRF token is sent correctly in fetch request
- Verify coach authorization (cannot update attendance for events outside their teams)
