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

- `delete_future_events(db, recurrence_group_id) -> int` — deletes all events with `event_date >= today` in the group, **including today's event if it shares the group**. Returns the count of deleted events.
- `count_future_events(db, recurrence_group_id) -> int` — counts events with `event_date >= today` in the group, including today.

### Route change

`POST /events/{event_id}/delete` (existing, requires `require_coach_or_admin` + CSRF) gains one new optional form field:

- `scope`: `"single"` (default) | `"future"`

Behavior:
- `scope="single"` — existing behavior: `db.delete(event)`, redirect to `/events`.
- `scope="future"` — only valid when `event.recurrence_group_id` is set. Calls `delete_future_events(db, event.recurrence_group_id)`. **No additional `db.delete(event)` call is needed** — the service already handles `event_date >= today`, which always includes the current event. Redirect to `/events`.
- If `scope="future"` is submitted for a non-recurring event (no `recurrence_group_id`), silently degrade to `"single"`.

Flash messages:
- Single: "Event deleted."
- Future: "Deleted {N} events in this series." where N is the return value of `delete_future_events()`.

### UI

On the event detail page, the existing delete button is replaced by a button that opens a `<dialog>`:

- **Non-recurring event:** Dialog shows event title, a simple "Are you sure?" message, Cancel + Delete buttons. Submits `scope=single`.
- **Recurring event:** Dialog shows two radio options:
  - "Delete only this event" (default selected)
  - "Delete this and all future events in this series ({N} upcoming)" — N is rendered server-side when the detail page loads, via `count_future_events()`. N includes the current event.
  - Cancel + Delete buttons. Submits whichever scope is selected.

The count `N` is injected into the template context at render time (no extra AJAX call needed). Pass `future_count=count_future_events(db, event.recurrence_group_id) if event.recurrence_group_id else 0` from the detail route.

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

Alembic migration required. All existing rows default to `NULL` (not borrowed). A row with `borrowed_from_team_id IS NOT NULL` is a "borrowed" attendance record.

### New endpoint: player search

`GET /players/search` — defined in `routes/players.py` (which registers under the `/players` prefix in `app/main.py`), so the final path is `/players/search`. Requires `require_coach_or_admin`. No CSRF (GET request).

Query params:
- `q` (string) — partial name match (case-insensitive, matches first or last name). Min 2 chars; return empty list if shorter.
- `exclude_event_id` (int, **required** in practice — the UI always supplies it) — used to (a) exclude players who already have an Attendance row for this event, and (b) resolve the event's `season_id` for `team_name` derivation.

Response: JSON array of `{id, full_name, team_name}`. `team_name` is derived from the player's highest-priority `PlayerTeam` row for the resolved `season_id` (from the event looked up via `exclude_event_id`). If `exclude_event_id` is absent or the event has no `season_id`, `team_name` is `null` for all results. Returns max 20 results.

### New endpoint: borrow action

`POST /attendance/{event_id}/borrow` — defined in `routes/attendance.py`. Requires `require_coach_or_admin` + CSRF (via `require_csrf` dependency, same as all other mutating attendance routes).

Form fields: `player_id` (int).

Behavior:
1. Look up event; if not found → `{ok: false, error: "event_not_found"}`.
2. Look up player by `player_id`; if not found or `player.is_active` is `False` → `{ok: false, error: "player_not_found"}`. (`is_active` is the `Player.is_active: Mapped[bool]` field.)
3. Check no `Attendance` row already exists for this `(event_id, player_id)` pair → `{ok: false, error: "already_attending"}` if duplicate.
4. Look up player's primary team for the event's season: highest-priority `PlayerTeam` where `player_id=player_id` and `season_id=event.season_id` (order by `priority ASC`, take first). If `event.season_id` is `None`, or no `PlayerTeam` row exists, `borrowed_from_team_id` is stored as `None` — this is not an error.
5. Create `Attendance(event_id=event_id, player_id=player_id, status="unknown", borrowed_from_team_id=...)`.
6. Return JSON `{ok: true, player_id, full_name, team_name}` where `team_name` is the team name or `null`.

### UI — attendance mark page (admin view)

An "Add borrowed player" button appears above the attendance table (admin view only, same guard as rest of admin view).

Clicking opens a `<dialog>`:
1. A text input for name search (debounced 300 ms, min 2 chars).
2. Results rendered as a clickable list: "Full Name — Team Name" (or "Full Name — no team" if unassigned).
3. Clicking a result selects it (highlighted). An "Add to event" button becomes enabled.
4. Submitting POSTs to `/attendance/{event_id}/borrow` via fetch with CSRF token from hidden field.
5. On `ok: true`, close dialog and append a new row to the attendance table without reload. The new row is added with status badge "Unknown" and the borrowed indicator.
6. On `ok: false`, keep the dialog open and show an inline error message below the search results: `"already_attending"` → "This player is already in the attendance list."; `"player_not_found"` → "Player not found or inactive."; `"event_not_found"` → "Event not found." (defensive fallback, should not occur in normal use).

**Tooltip indicator:** Borrowed players show a small ⟳ icon after their name in the table. On hover, a CSS tooltip reads: "Borrowed from [Team Name]" (or "Borrowed — no home team" if `borrowed_from_team_id` is null).

**Editing borrowed players:** No special case. The existing Edit dialog works as-is. Borrowed players can be set to any status. They are not removed or affected when their home team's attendance is auto-managed.

**Removing a borrowed player:** Out of scope. A future iteration can add explicit removal.

### Template context

The `GET /attendance/{event_id}` route queries all `Attendance` rows. It will eager-load `Attendance.borrowed_from_team` (SQLAlchemy relationship to `Team`) so `att.borrowed_from_team.name` is available in the template without N+1 queries.

---

## Files to Change

| File | Change |
|---|---|
| `alembic/versions/*.py` | New migration: add `borrowed_from_team_id` to `attendance` |
| `models/attendance.py` | Add `borrowed_from_team_id` column + `borrowed_from_team` relationship |
| `routes/events.py` | Enhance `event_delete` to handle `scope` param; pass `future_count` to detail template |
| `routes/players.py` | Add `GET /players/search` endpoint |
| `routes/attendance.py` | Add `POST /attendance/{event_id}/borrow` |
| `templates/events/detail.html` | Replace delete button with dialog; show recurrence options when `future_count > 0` |
| `templates/attendance/mark.html` | Add "Add borrowed player" button, dialog, JS, tooltip indicator |
| `static/css/main.css` | Tooltip styles for borrowed indicator |

## Testing

- `test_event_delete_single` — deletes one event, others in group untouched.
- `test_event_delete_future` — deletes current + all future in group via `delete_future_events`; past events untouched; flash shows correct N.
- `test_event_delete_future_nonrecurring_falls_back` — `scope=future` on non-recurring degrades to single delete.
- `test_borrow_creates_attendance_with_team` — happy path; `borrowed_from_team_id` set to player's highest-priority team for event season.
- `test_borrow_no_season_stores_null_team` — event with `season_id=None`; borrow succeeds with `borrowed_from_team_id=None`.
- `test_borrow_duplicate_rejected` — `already_attending` error.
- `test_borrow_player_search_excludes_attending` — search endpoint excludes players with existing attendance for the event.
- `test_borrow_inactive_player_rejected` — player with `is_active=False` returns `player_not_found` error.
