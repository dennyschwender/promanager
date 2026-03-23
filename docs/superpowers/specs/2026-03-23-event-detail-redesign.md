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
- Inline badges: event type, presence type, recurring indicator (only if `event.recurrence_group_id` is set)
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

Only rendered when `event.presence_type != "no_registration"`. When `no_registration`, show a short note: "Attendance tracking is disabled for this event."

**Column layout** (CSS flex/grid, responsive):
One card per status bucket: **Present · Absent · Maybe · Unknown**

Rules:
- Each column shows a header badge with count: e.g. `Present (8)`
- Empty columns are **hidden** on initial render
- When a player is moved **into** a hidden column, that column becomes visible
- When the last player is moved **out** of a column, it is hidden again
- Player names listed vertically inside each column
- Each player name is a clickable element (button styled as text link)

**Player popover:**
- A single shared popover DOM node is created once and reused for each player (not per-player nodes)
- Triggered by clicking a player name; positioned below the clicked element using `getBoundingClientRect()` + absolute positioning relative to the page
- Shows player's name as popover title
- Four status buttons in a row: Present / Absent / Maybe / Unknown — current status visually highlighted via a CSS class
- Note textarea pre-filled with the player's existing note (passed via `data-note` attribute on the player element)
- Save button — disabled while fetch is in-flight to prevent double-submit; re-enabled on completion
- Close/cancel button
- Clicking outside the popover closes it (document-level click listener with `closest()` guard)

---

## Backend Changes

### JSON response branch on existing attendance endpoint

Modify `POST /attendance/{event_id}/{player_id}` to detect AJAX callers via the `Accept: application/json` request header:

- If `Accept: application/json` → return JSON, do not redirect
- Otherwise → existing redirect behaviour is preserved exactly (no breaking change for form-based callers)

**Success response:**
```json
{ "ok": true, "status": "present", "note": "..." }
```

**Error responses (all return `ok: false`):**
```json
{ "ok": false, "error": "unauthorized" }   // 403
{ "ok": false, "error": "not_found" }      // 404
{ "ok": false, "error": "invalid_status" } // 400
```

Frontend shows a brief inline error message on failure (e.g. "Could not save. Please try again.") without closing the popover.

Authorization logic is unchanged — same checks apply whether request is AJAX or form.

### Event detail route (`/events/{event_id}`)

No structural changes needed. The `summary` dict already groups players by bucket with their notes. The template change is purely frontend.

The summary dict must include each player's current note alongside their name so it can be embedded as a `data-note` attribute on the player element. Verify that `summary[bucket]` contains `Attendance` objects (with `.note`) not bare `Player` objects. If needed, adjust the route to include note data.

---

## Frontend Implementation

### Template: `templates/events/detail.html`

- Rewrite layout per design above
- Attendance columns rendered server-side (Jinja2); JavaScript only handles popover open/close and AJAX submit
- No external JS libraries needed — vanilla JS
- Popover styled inline (background, border, border-radius, box-shadow, padding, z-index) so it works without Pico CSS component support

### JavaScript (inline in template, ~100 lines)

```
State:
  activePlayerId = null
  activePlayerEl = null

openPopover(playerEl):
  close any existing popover
  read data-player-id, data-status, data-note from playerEl
  populate popover fields
  position popover using getBoundingClientRect() + window.scrollY
  set activePlayerId, activePlayerEl

closePopover():
  hide popover DOM node
  reset activePlayerId = null

submitStatus(eventId, playerId, status, note):
  disable save button
  fetch POST /attendance/{eventId}/{playerId}
    headers: { Accept: application/json, X-CSRFToken: <meta csrf> }
    body: FormData with status, note, csrf_token
  on ok=true:
    movePlayer(playerId, status, note)
    closePopover()
  on ok=false or network error:
    show inline error in popover
    re-enable save button

movePlayer(playerId, newStatus, note):
  find player element by data-player-id
  update its data-status and data-note attributes
  remove from current column list
  append to target column list
  update both column counts
  hide source column if now empty
  show target column if it was hidden
```

CSRF token read from `<meta name="csrf-token">` (already present in the base template).

---

## Out of Scope

- Drag-and-drop between columns (popover is sufficient and more accessible)
- Bulk status changes
- Attendance history per player (exists on player detail page)
- Modifying the separate `/attendance/{event_id}` page (keep as-is for player self-reporting)

---

## Testing

**Automated (add to `test_attendance.py`):**
- `test_update_attendance_json_response` — POST with `Accept: application/json`, assert `{ ok: true }` and correct status
- `test_update_attendance_json_unauthorized` — coach tries to update attendance for a different team's event, assert `{ ok: false, error: "unauthorized" }`
- `test_update_attendance_form_redirect_unchanged` — POST without JSON header still redirects (regression guard)

**Manual checklist:**
- Open popover → correct player name, status highlighted, note pre-filled
- Change status → player moves to correct column, count updates
- Source column hides when its last player is moved out
- Target column appears when a player is moved in (from a previously hidden column)
- Save button disabled during in-flight request (simulate with slow network)
- Network error / 403 → inline error shown, popover stays open
- Click outside popover → closes
- `no_registration` event → attendance section replaced by note, no JS errors
- Coach auth: cannot update attendance for events outside their team
