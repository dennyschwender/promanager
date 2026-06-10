# Dashboard Redesign

Role-aware dashboard that complements (does not duplicate) All Events and Reports.

## Summary

Replace the current Dashboard (which shows a "next 5 events" table overlapping with All Events) with role-specific widget-based views:

- **Players (members):** personal attendance rate, next event card, unread notifications, my absences
- **Coaches/Admins:** team-wide stats (attendance %, pending count, injured/absent count), compact upcoming events, watch list, recent chat feed, quick actions (admin)

Reports removed from member nav — coach/admin only.

## Player Dashboard

Replaces `/dashboard` for users with `role="member"`. If the member has no linked player, they see a minimal placeholder ("You are not linked to any player yet").

### Layout

Four-card grid in a 2×2 layout:

| My Attendance | Next Event |
|---|---|
| Unread Notifications | My Absences |

### Widget: My Attendance

- **Data:** computed from `Attendance` for the logged-in player across all events in the active season
- **Display:** percentage (e.g. "78%"), with sub-row "Trainings 82% · Matches 60%"
- **Click:** → `/reports/my` (existing player report page)

### Widget: Next Event

- **Data:** first upcoming event for any team the player is in (filtered by active season, ordered by `event_date` ASC)
- **Display:** title, date, time, location; colored status button (same inline attendance popover pattern already used in dashboard and events list)
- **Status button:** same JS popover as current dashboard — POST to `/attendance/{event_id}/{player_id}`
- **Click on title:** → `/events/{id}`

### Widget: Unread Notifications

- **Data:** last 3 unread `Notification` records for the user/player, ordered by `created_at` DESC
- **Display:** count badge, then 3 preview lines (truncated title + event name if linked)
- **Click on a line:** → `/events/{event_id}` or fallback to `/notifications`

### Widget: My Absences

- **Data:** active absences (`PlayerAbsence` where `end_date >= today` or `rrule_until >= today`)
- **Display:** if none → "No active absences" + "Manage Absences" button
- **Button:** → `/players/{player_id}/absences`

### Edge cases

- Member with no linked player: show alert "You are not linked to any player. Contact your coach." No widgets.
- Member with no events in active season: "No upcoming events scheduled." No next-event widget.
- Member with no unread notifications: hide the notification widget entirely (2×2 becomes 1×2 or 2×1).
- No active season: warning banner (same as current dashboard), widgets based on all events.

## Coach/Admin Dashboard

Replaces `/dashboard` for users with `role="admin"` or `role="coach"`.

### Layout

```
[ three stat cards in a row ]
[ upcoming events  |  watch list   ]
[ recent chat activity          ]
[ quick actions (admin only)    ]
```

### Stat Cards

Three cards in a horizontal row:

1. **Team Attendance** — overall attendance rate % for the active season, with trend arrow (▲/▼ vs previous 30-day window). Click → `/reports/season/{active_season_id}`.
2. **Pending** — count of `Attendance` with `status="unknown"` across upcoming events. Subtitle: "X unknowns across Y events". Click → `/events`.
3. **Injured/Absent** — count of players with `membership_status="injured"` or an active period absence. Subtitle: "X injured · Y period absences". Click → `/players` with status filter.

### Widget: Upcoming Events

Compact list (not table) of next ~5 events with:
- Relative date label ("Tomorrow", "Sun 14", etc.)
- Event title
- Pending count "(5/12 unknown)" in muted text
- Click → `/events/{id}`

### Widget: Watch List

Players needing attention, sorted by severity:
- **Red:** missed 3+ consecutive events (count)
- **Yellow:** missed 1-2 consecutive events
- **Green:** injured until a specific date
- Click player name → `/players/{id}`
- Click the absence note → `/players/{id}/absences`

### Widget: Recent Chat Activity

Last 5 `EventMessage` records across all events the coach/admin has access to, ordered by `created_at` DESC.
- Display: author name, truncated body, event name
- Click → `/events/{event_id}`

### Admin extras

A "Quick Actions" row below all widgets, same as current dashboard: + New Season, + New Team, + New Player, + New Event, + Register User.

### Data: Attendance rate per player (for watch list)

Computed as: `COUNT(status='present') / COUNT(*)` per player, across events with `event_date <= today`. Stale players (no attendance records in 30+ days) excluded from the watch list.

### Coach scoping

Coaches see data only for teams they are assigned to (`UserTeam`). The stat cards, upcoming events, watch list, and chat feed are all filtered by `get_coach_teams()`.

## Nav Changes

- `Reports` link hidden from member nav
- `Dashboard` link remains for all roles (now shows different content per role)

## Route Changes

`routes/dashboard.py` — restructure the `dashboard()` handler to branch on user role:
- `is_admin` or `is_coach` → coach dashboard query + render
- else → player dashboard query + render

Remove the "next 5 events" table query from the dashboard route. Keep only new widget queries.

## Template Files

- `templates/dashboard/index.html` — replace entirely with role-switched content
- `templates/dashboard/player.html` — player widgets (new)
- `templates/dashboard/coach.html` — coach/admin widgets (new)

Or keep a single `index.html` with Jinja2 `{% if user.is_admin or user.is_coach %}...{% else %}...{% endif %}` branching — whichever keeps the template readable.

## Template for Member Nav

In `templates/base.html`:
- Add `{% if user.is_admin or user.is_coach %}` around the Reports nav link.

## Testing

- Test player dashboard: member with linked player, no linked player, no active season, no events, no notifications, active absences
- Test coach dashboard: coach with teams, coach without teams, admin view
- Test nav: Reports link hidden for members
- Test edge: member dashboard when player has no attendance records yet (divide-by-zero on rate)

## Out of Scope

- Charts/visualizations (text-based percentages only)
- Drag-and-drop widget customization
- Notification read-through from dashboard (users still go to `/notifications` to bulk-mark)
- Historical trend comparisons for coach stat cards (just a simple 30-day delta arrow)