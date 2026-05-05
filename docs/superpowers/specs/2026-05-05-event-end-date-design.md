# Event End Date Design

## Goal
Support multi-day events by adding an optional `event_end_date` field to the Event model.

## Model
- Add `event_end_date: Mapped[date | None]` (nullable) to `models/event.py`
- Alembic migration: `event_end_date DATE NULL`

## Validation
- `event_end_date >= event_date` when set (server + client)
- Nullable — single-day events unaffected

## Display Format
| Condition | Format |
|-----------|--------|
| No end date | current (unchanged) |
| Same month | `01–03 May 2026` |
| Cross-month | `30 Apr – 02 May 2026` |
| Cross-year | `30 Dec 2025 – 02 Jan 2026` |

Applied in: events list date column, event detail header.

## Upcoming / Past Logic
`effective_end = event_end_date or event_date`
Event is past when `effective_end < today`.

## Form
- Optional end date field in create/edit event form
- Placed after `event_date` field
- Client-side: disable end dates before start date via JS
- Label: "End Date (optional)"

## Recurrence
End date applies per event instance — each occurrence can have its own span. No change to recurrence logic.

## Files to Change
- `models/event.py` — add field
- `alembic/versions/` — new migration
- `routes/events.py` — upcoming/past split uses effective_end; form validation
- `templates/events/list.html` — date range display
- `templates/events/detail.html` — date range display
- `templates/events/form.html` (or equivalent) — end date input field
