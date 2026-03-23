# Event Deletion (Recurrence-Aware) & Player Borrowing — Design Spec

## Goal

Two independent event-level features:
1. **Recurrence-aware deletion** — delete a single event or all future events in its series.
2. **Player borrowing** — add a player from another team to a single event's attendance, with a visual indicator.

## Architecture

Both features extend existing patterns: the attendance route/model and the event delete route. No new models beyond a single new column. No new pages — both features surface as dialogs on existing pages.

---

## Feature 1: Recurrence-Aware Event Deletion

### Data

No schema changes. The `Event` model already stores `recurrence_group_id` (nullable UUID string) and `recurrence_rule`. The service layer already provides:

- `delete_future_events(db, recurrence_group_id) -> int` — deletes all events with `event_date >= today` in the group.
- `count_future_events(db, recurrence_group_id) -> int` — counts upcoming events in the group.

### Route change

`POST /events/{event_id}/delete` gains one new optional form field:

- `scope`: `"single"` (default) | `"future"`

Behavior:
- `scope="single"` — existing behavior: `db.delete(event)`, redirect to `/events`.
- `scope="future"` — only valid when `event.recurrence_group_id` is set. Calls `delete_future_events(db, event.recurrence_group_id)`, then also deletes the current event if it wasn't caught (i.e., if `event_date == today`). Redirect to `/events`.
- If `scope="future"` is submitted for a non-recurring event, treat as `"single"` (safe fallback).

Flash messages:
- Single: "Event deleted."
- Future: "Event and {N} future events deleted."

### UI

On the event detail page, the existing delete button is replaced by a button that opens a `<dialog>`:

- **Non-recurring event:** Dialog shows event title, a simple "Are you sure?" message, Cancel + Delete buttons. Submits `scope=single`.
- **Recurring event:** Dialog shows two radio options:
  - "Delete only this event" (default selected)
  - "Delete this and all future events in this series ({N} upcoming)" — N is rendered server-side when the detail page loads, via `count_future_events()`.
  - Cancel + Delete buttons. Submits whichever scope is selected.

The count `N` is injected into the template at render time (no extra AJAX call needed).

### Error handling

- Event not found → redirect to `/events` (existing behavior).
- `scope="future"` on non-recurring → silently degrade to `"single"`.

---

## Feature 2: Player Borrowing

### Data

**One new column** on the `Attendance` table:

```
borrowed_from_team_id  INTEGER  NULL  FK → teams(id) ON DELETE SET NULL
```

Alembic migration required. All existing rows default to `NULL` (not borrowed).

### New endpoint: player search

`GET /players/search` — lightweight JSON endpoint (coach/admin only).

Query params:
- `q` (string) — partial name match (case-insensitive, matches first or last name).
- `exclude_event_id` (int, optional) — exclude players who already have an Attendance row for this event.

Response: JSON array of `{id, full_name, team_name}`. `team_name` is the player's team in the same season as the event (highest-priority `PlayerTeam` row for that season), or `null` if none. Returns max 20 results.

### New endpoint: borrow action

`POST /attendance/{event_id}/borrow` (coach/admin, CSRF required).

Form fields: `player_id` (int).

Behavior:
1. Validate event exists and player exists and is active.
2. Check no Attendance row already exists for this player/event pair.
3. Look up player's primary team for the event's season (highest-priority `PlayerTeam` where `season_id = event.season_id`). Store its `team_id` as `borrowed_from_team_id`.
4. Create `Attendance(event_id=event_id, player_id=player_id, status="unknown", borrowed_from_team_id=...)`.
5. Return JSON `{ok: true, player_id, full_name, team_name, status: "unknown"}`.

Error responses (JSON):
- `{ok: false, error: "already_attending"}` — duplicate.
- `{ok: false, error: "player_not_found"}` — invalid player_id.
- `{ok: false, error: "event_not_found"}` — invalid event_id.

### UI — attendance mark page (admin view)

An "Add borrowed player" button appears above the attendance table.

Clicking opens a `<dialog>`:
1. A text input for name search (debounced 300 ms, min 2 chars).
2. Results rendered as a clickable list: "Full Name — Team Name" (or "— no team" if unassigned).
3. Clicking a result selects it (highlighted row). A "Add to event" button becomes enabled.
4. Submitting POSTs to `/attendance/{event_id}/borrow` via fetch.
5. On `ok: true`, close dialog and append a new row to the attendance table without reload.

**Tooltip indicator:** Borrowed players show a small ⟳ icon after their name in the table. On hover, a CSS tooltip reads: "Borrowed from [Team Name]" (or "Borrowed — no home team" if `borrowed_from_team_id` is null).

**Editing borrowed players:** No special case. The existing Edit dialog works as-is. Borrowed players can be set to any status. They are not removed when their home team's attendance is managed.

**Removing a borrowed player:** Out of scope for this feature. Coaches can set their status to any value via the Edit dialog. A future iteration can add explicit removal.

### Template context

The `GET /attendance/{event_id}` route already queries all `Attendance` rows for the event. It will now also join `borrowed_from_team_id` → `Team.name` so the template can render the tooltip. This requires an eager-load of the team relationship on `Attendance` (or a simple dict lookup built in the route).

---

## Files to Change

| File | Change |
|---|---|
| `alembic/versions/*.py` | New migration: add `borrowed_from_team_id` to `attendance` |
| `models/attendance.py` | Add `borrowed_from_team_id` column + `borrowed_from_team` relationship |
| `routes/events.py` | Enhance `event_delete` to handle `scope` param |
| `routes/attendance.py` | Add `POST /attendance/{event_id}/borrow` and `GET /players/search` |
| `templates/events/detail.html` | Replace delete button with dialog (pass `future_count` to template) |
| `templates/attendance/mark.html` | Add "Add borrowed player" button, dialog, JS, tooltip styles |
| `static/css/main.css` | Tooltip styles for borrowed indicator |

## Testing

- `test_event_delete_single` — deletes one event, others in group untouched.
- `test_event_delete_future` — deletes current + all future in group, past untouched.
- `test_event_delete_future_nonrecurring_falls_back` — safe fallback.
- `test_borrow_creates_attendance_with_team` — happy path.
- `test_borrow_duplicate_rejected` — `already_attending` error.
- `test_borrow_player_search_excludes_attending` — search excludes existing attendees.
- `test_borrow_inactive_player_rejected` — inactive player not borrowable.
