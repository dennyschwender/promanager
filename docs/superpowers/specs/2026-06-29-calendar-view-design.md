# Calendar Month Grid View

## Summary

Interactive month-grid calendar for events, server-rendered with vanilla JS enhancements. Replaces/complements the existing paginated event list as the primary navigation point.

## Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/events/calendar` | optional_user | Month grid (defaults to current month) |
| `GET` | `/events/calendar?year=2026&month=6` | optional_user | Specific month |
| `GET` | `/api/events/calendar-day?date=2026-06-15` | optional_user | HTML snippet for a single day's events |

New module: `routes/calendar_view.py`. Added to `_routers` in `app/main.py` as `("routes.calendar_view", "", "events")`.

Same query filters as list view: `?team_id=X&season_id=Y` persist across month navigation. Nav link changes from `/events` to `/events/calendar`.

## Access Control

Same as list view — role-based event visibility:
- **admin**: all events
- **coach**: events for their teams (`get_coach_teams`)
- **member**: events for teams they're part of (resolved via Player → PlayerTeam → team_ids)
- **unauthenticated**: public events (none currently shown, but the list view is public)

## Server: Data Flow

Calendar handler:
1. Parse `year`, `month` from query (default: today). Validate range.
2. Compute calendar grid boundaries: first day of month, last day of month, leading/lagging days from prev/next month to fill 7-column grid (Monday-start weeks).
3. Query events with `event_date` IN [grid_start, grid_end] with role-filtered query (same base query as `events_list`).
4. Build `days[]` list — each day object:
   - `date` (date object)
   - `is_current_month` (bool) — dimmed if False
   - `is_today` (bool) — highlighted
   - `events` — list of dicts: `{id, title, event_type, event_time, meeting_time, location}`
5. Compute prev/next month/year for navigation arrows.
6. Pass to template.

## Template: `templates/events/calendar.html`

Extends `base.html`. Sections:
1. **Filter bar** — season dropdown, team dropdown (same controls as list view)
2. **Month navigation** — `‹` prev / `Month YYYY` / `›` next
3. **Day header row** — Mon Tue Wed Thu Fri Sat Sun
4. **Grid** — 7 columns × up to 6 rows:
   - Each cell: date number (top-left), event items below
   - Event item format: `[HH:MM] Event title` — uses `meeting_time` if present, falls back to `event_time`. If no time, shows title only.
   - Event dot colored by `event_type`: match=red, training=blue, other=gray
   - Today's date: highlighted circle/badge
   - Outside-month days: dimmed text, no background
5. **Day detail panel** — hidden `<div>` below grid, rendered via JS

## Client: JS Enhancements

In `static/js/calendar.js` (new file):

1. **Month navigation** — prev/next buttons call `fetch` with `?year=&month=`, replace grid HTML inline (no full page reload). Update browser history via `history.pushState`.

2. **Day click handler** — click on day cell background (not on an event `<a>`):
   - Call `GET /api/events/calendar-day?date=YYYY-MM-DD` returning rendered HTML
   - Show day detail panel below grid with returned HTML
   - Panel contains: header with date, list of events (time + title + link to detail), close button, "View all" link → `/events?date_from=...&date_to=...`
   - Clicking outside panel or close button hides it

3. **Filter change** — season/team dropdown change triggers re-fetch of current month with new filters.

Follows existing project patterns: vanilla `fetch()`, no framework, progressive enhancement (calendar works with JS disabled via full page reloads).

## Day Detail API: `GET /api/events/calendar-day`

Returns rendered HTML snippet (not JSON — matches existing pattern of server-rendered fragments):

```html
<div class="day-detail-header">Events on June 15, 2026</div>
<ul class="day-detail-list">
  <li><a href="/events/1">18:30 Training - U15</a></li>
  <li><a href="/events/2">10:00 Match vs Team X</a></li>
</ul>
<a href="/events?date_from=2026-06-15&date_to=2026-06-15" class="day-detail-all">View all</a>
```

Same authentication and visibility filtering as the main calendar query.

## CSS Additions (`static/css/main.css`)

New styles needed (add to existing file):
- `.calendar-grid` — CSS Grid, 7 equal columns
- `.calendar-day-cell` — cell with min-height, relative positioning
- `.calendar-day-number` — date number in top-left
- `.calendar-day-number--today` — highlighted circle
- `.calendar-day-number--other-month` — dimmed text
- `.calendar-event-item` — small event entry within cell, colored left border by type
- `.calendar-nav` — prev/next month bar
- `.calendar-day-detail` — panel below grid
- `.calendar-filter-bar` — filter controls row
- `.calendar-header-day` — day name header cell
- Type color classes: `.event-type-match`, `.event-type-training`, `.event-type-other`
- Mobile: stack to single-column list below 600px

## Testing

### Unit / Integration tests (in `tests/test_calendar_view.py` or add to `tests/test_events.py`)

| Test | What to verify |
|------|---------------|
| `test_calendar_page_returns_200` | GET `/events/calendar` returns 200 |
| `test_calendar_page_public` | Unauthenticated GET returns 200 |
| `test_calendar_with_events` | Month with events renders event items in day cells |
| `test_calendar_empty_month` | Month with no events renders empty cells |
| `test_calendar_month_navigation` | `?year=2026&month=7` loads correct month |
| `test_calendar_respects_team_filter` | `?team_id=X` only shows events for that team |
| `test_calendar_day_api_returns_events` | `/api/events/calendar-day` returns events for that date |
| `test_calendar_day_api_404_no_events` | `/api/events/calendar-day` with no events returns empty list (200) |
| `test_calendar_day_api_requires_same_access` | Day API respects role-based visibility |
| `test_calendar_member_sees_own_events_only` | Member doesn't see events from teams they're not in |
| `test_calendar_coach_sees_their_teams` | Coach sees events for their teams only |

## Navigation Integration

- Nav bar "Events" link: change `href` from `/events` to `/events/calendar`
- Calendar page includes a "List view" link to `/events` for users who prefer the table view
- Active nav class: `path.startswith('/events')` still works for both routes