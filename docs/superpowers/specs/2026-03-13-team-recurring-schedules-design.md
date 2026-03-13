# Team Recurring Schedules — Design Spec

**Goal:** Allow admins to define multiple recurring event schedules (e.g. Tuesday training, Thursday training) directly on the team edit page, with automatic event generation and selective regeneration when schedules change.

**Architecture:** A new `TeamRecurringSchedule` model stores schedule definitions linked to a team. On team save, the server generates `Event` rows for each schedule. A `recurrence_group_id` UUID links each schedule to its generated events, enabling precise change detection and selective regeneration. Change detection uses a server-side two-step POST with a confirmation step.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, SQLite, Alembic, existing `_advance_date()` helper, existing `ensure_attendance_records()` service.

**Note:** The `Event` model already has `recurrence_group_id` (String(36), nullable, indexed) and `recurrence_rule` (String(32), nullable) columns — no migration needed for the events table.

---

## Data Model

### New table: `team_recurring_schedules`

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer | PK | |
| `team_id` | Integer | FK → teams.id CASCADE DELETE, NOT NULL, index | |
| `title` | String(256) | NOT NULL | e.g. "Tuesday Training" |
| `event_type` | String(32) | NOT NULL, default "training" | training / match / other |
| `recurrence_rule` | String(32) | NOT NULL | weekly / biweekly / monthly |
| `start_date` | Date | NOT NULL | first occurrence date |
| `end_date` | Date | nullable | if null, fall back to season end_date |
| `event_time` | Time | nullable | |
| `event_end_time` | Time | nullable | |
| `location` | String(256) | nullable | |
| `meeting_time` | Time | nullable | |
| `meeting_location` | String(256) | nullable | |
| `presence_type` | String(32) | NOT NULL, default "normal" | |
| `description` | Text | nullable | |
| `recurrence_group_id` | String(36) | NOT NULL, unique, index | UUID assigned at creation; links schedule → generated events |

### Modified: `models/team.py`

Add relationship:
```python
recurring_schedules: Mapped[list[TeamRecurringSchedule]] = relationship(
    "TeamRecurringSchedule",
    back_populates="team",
    cascade="all, delete-orphan",
    lazy="select",
)
```

---

## Default Event Title

When a user adds a new schedule row, the title field is pre-filled (via JS) with a suggested default:

```
{team_name} - {event_type_capitalized} {day_of_week_if_weekly}
```

- `team_name` = the team's current name (passed to template as a JS variable)
- `event_type_capitalized` = e.g. "Training", "Match", "Other"
- `day_of_week_if_weekly` = derived from the `start_date` field using JS `Date.getDay()`, shown only when recurrence_rule is "weekly" (e.g. "Tuesday"). Omitted for biweekly/monthly.

Examples:
- Weekly training starting on a Tuesday → `"FC Zurich - Training Tuesday"`
- Monthly match → `"FC Zurich - Match"`

The title is always editable; the default is a suggestion only. The JS updates the suggestion live as the user changes start_date, event_type, or recurrence_rule — but only if the title has not been manually edited yet (tracked with a `data-auto` attribute on the input).

---

## UI

The team edit form (`/teams/{id}/edit`) gets a new **"Recurring Schedules"** fieldset below the existing fields.

### Schedule row fields (per schedule)
- Title (text, required) — pre-filled with default suggestion (see above)
- Event Type (select: Training / Match / Other)
- Recurrence (select: Weekly / Biweekly / Monthly)
- Start Date (date input, required)
- End Date (date input, optional — hint: "leave blank to use season end date")
- Time / End Time (time inputs)
- Location (text)
- Meeting Time / Meeting Location (text, hidden under a "Show details" toggle per row)
- Remove button (×) per row

### Controls
- "+ Add Schedule" button appends a new blank row (JS, no page reload)
- Each row has a hidden `schedule_id` field (empty for new rows)

---

## Save Flow

### Distinguishing first POST from confirmation POST

A hidden field `_confirm_step` is included in all form submissions:
- `_confirm_step = ""` (absent/empty) → first POST (normal save)
- `_confirm_step = "1"` → second POST (confirmation)

### First POST (normal save)

All DB work in this step is deferred — nothing is committed until all change detection passes cleanly.

1. Parse all submitted schedule rows from form data (see "Form field naming" below).
2. Load existing schedules for this team from DB.
3. For each submitted row:
   - **New** (no `schedule_id`): assign a new UUID to `recurrence_group_id`. Mark for deferred generation.
   - **Unchanged** (all key fields match stored values): no event changes. Propagate `title`, `description` and other non-key fields in-place to future events (`event_date >= today`).
   - **Changed** (any key field differs): flag for confirmation. Compute count of future events with matching `recurrence_group_id`.
4. For each stored schedule not present in submitted rows: flag for deletion confirmation. Compute count of future events.
5. Also detect effective-end-date change: if the team's `season_id` changed AND any schedule has `end_date = null`, flag those schedules for confirmation.
6. **If any flagged items exist:** nothing is committed. Re-render the team form with `_confirm_step=1`, a yellow warning section listing each flagged schedule with:
   - Schedule title and what changed (or "will be removed")
   - Count of future events that would be deleted (with note: "manually edited events will also be deleted")
   - Checkbox `confirm_schedule_{id}` (unchecked by default): "Delete existing future events and regenerate"
   - If a schedule is flagged for removal and user leaves checkbox unchecked: the schedule row is **kept** and events are untouched.
   - The full submitted schedule state is serialised as HMAC-signed JSON in `_schedules_json` (signed with `SECRET_KEY`) to carry it through to the second POST.
7. **If no flagged items:** execute all deferred operations in a single transaction, commit, redirect to `/teams/{id}/edit?saved=1`.

### Second POST (confirmation step)

Identified by `_confirm_step = "1"`. The server:

1. Verifies the HMAC signature of `_schedules_json`. If invalid, reject with 400.
2. Deserialises `_schedules_json` to recover the full submitted schedule state.
3. Executes in a single transaction:
   - For each **new** schedule (no original `schedule_id`): assign UUID, save, generate events.
   - For each **changed** schedule with `confirm_schedule_{id}` checked: delete future events (`event_date >= today`) with old `recurrence_group_id`, assign new UUID, save updated fields, regenerate events.
   - For each **changed** schedule with checkbox unchecked: save updated schedule fields, do NOT touch events.
   - For each **removed** schedule with `confirm_schedule_{id}` checked: delete future events, delete schedule.
   - For each **removed** schedule with checkbox unchecked: keep the schedule and events untouched.
   - For each **unchanged** schedule: propagate non-key field changes in-place to future events.
4. Commit, redirect to `/teams/{id}/edit?saved=1`.

**Known limitation:** No optimistic locking. If two admins submit the team form simultaneously, the last write wins. Treated as an acceptable limitation for the current scope.

### Form field naming

JS re-indexes all rows to 0..N-1 on form submit (removing gaps from deleted rows). Fields per row at index `i`:
- `sched_id_{i}` — empty for new rows, schedule PK for existing
- `sched_title_{i}`, `sched_event_type_{i}`, `sched_rule_{i}`
- `sched_start_{i}`, `sched_end_{i}`
- `sched_time_{i}`, `sched_end_time_{i}`
- `sched_location_{i}`, `sched_meeting_time_{i}`, `sched_meeting_location_{i}`
- `sched_presence_{i}`, `sched_desc_{i}`
- `sched_count` — total number of rows after re-indexing (N)

---

## Event Generation

For a given schedule:

1. Determine the end date: `schedule.end_date` if set, else `team.season.end_date` if the team has a season with an end date. If neither exists, return a validation error: _"Set an end date on the schedule or assign the team to a season with an end date."_
2. Validate: `start_date <= end_date`. If not, validation error: _"Start date must be on or before end date."_
3. Starting from `schedule.start_date`, generate dates using `_advance_date(date, rule)` until `> end_date`. Include `start_date` itself as the first occurrence. Monthly rule: same day next month, capped to last day of that month (existing `_advance_date` behaviour).
4. For each date, create an `Event` with:
   - All fields from the schedule (title, event_type, times, location, etc.)
   - `team_id = team.id`
   - `season_id = team.season_id`
   - `recurrence_group_id = schedule.recurrence_group_id`
   - `recurrence_rule = schedule.recurrence_rule`
5. Call `ensure_attendance_records(db, event)` for each created event.
6. All inserts are `db.add()`; a single `db.commit()` is issued by the caller after all schedules are processed.

---

## Change Detection

A schedule is considered **changed** (triggers confirmation + deletion/regeneration) if any of these fields differ from the stored value:
`start_date`, `end_date`, `recurrence_rule`, `event_type`, `event_time`, `event_end_time`, `location`, `meeting_time`, `meeting_location`, `presence_type`.

Additionally, a schedule with `end_date = null` is flagged if the team's `season_id` changed.

**Non-triggering changes** (propagated in-place to future events without confirmation):
`title`, `description`. These are updated directly on existing `Event` rows where `event.recurrence_group_id = schedule.recurrence_group_id AND event.event_date >= today`.

---

## Edge Cases

- **No season / no end date**: validation error shown inline on the schedule row; that schedule is skipped. Other schedules with explicit end dates proceed normally.
- **`start_date > end_date`**: validation error: _"Start date must be on or before end date."_
- **Past events**: never deleted during regeneration — only `event_date >= today` are touched.
- **Start date in the past**: allowed; generation starts from `start_date` and may produce no future events. Proceed without warning.
- **Manually edited events**: the confirmation warning explicitly notes that all future events in the series will be deleted and replaced, including any that were manually edited. This is expected behaviour.
- **Duplicate schedules**: no uniqueness constraint; allowed.
- **Season has no end date**: treated the same as no season — validation error if schedule also has no explicit end date.
- **All confirmation checkboxes unchecked**: second POST saves all schedule field changes, leaves all events untouched.
- **Zero occurrences generated** (e.g. start_date == end_date and rule skips past it): save the schedule with no events created; no error.

---

## Files

| Action | File |
|---|---|
| Create | `models/team_recurring_schedule.py` |
| Create | `alembic/versions/<timestamp>_add_team_recurring_schedules.py` |
| Modify | `models/team.py` — add `recurring_schedules` relationship |
| Modify | `models/__init__.py` — export new model (Alembic `env.py` imports from here) |
| Modify | `routes/teams.py` — schedule parse, generate, change-detect, HMAC logic |
| Modify | `templates/teams/form.html` — new fieldset + JS for dynamic rows and default title suggestion |

Event generation logic lives in `routes/teams.py`, reusing `_advance_date` imported from `routes/events.py`.

---

## Testing

- Unit test: event generation for weekly / biweekly / monthly rules
- Unit test: change detection correctly identifies changed vs unchanged schedules (key field change vs non-key)
- Unit test: past events are not deleted on regeneration
- Unit test: end_date fallback to season end_date
- Unit test: validation error when no end_date available (neither schedule nor season)
- Unit test: validation error when start_date > end_date
- Unit test: `recurrence_group_id` UUID assigned before event generation for new schedules
- Unit test: title/description-only change propagates in-place, no events deleted
- Unit test: season change flags schedules with null end_date
- Unit test: HMAC signature verification rejects tampered `_schedules_json`
- Integration test: full save flow (new schedule → events created with correct recurrence_group_id)
- Integration test: changed schedule → confirmation step → events regenerated with new UUID
- Integration test: removed schedule with confirmation → future events deleted, schedule deleted
- Integration test: removed schedule without confirmation → schedule and events kept
- Integration test: confirmation unchecked for changed schedule → fields saved, events untouched
