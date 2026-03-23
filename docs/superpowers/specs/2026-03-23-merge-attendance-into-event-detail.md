# Merge Attendance Page into Event Detail — Design Spec

## Goal

Eliminate the standalone `/attendance/{event_id}` page. All attendance functionality moves into the event detail page (`/events/{event_id}`). The attendance GET route is deleted entirely.

---

## Route Changes

### Remove
- `GET /attendance/{event_id}` — handler deleted from `routes/attendance.py`
- `templates/attendance/mark.html` — template deleted

### Keep, but update redirect fallbacks
- `POST /attendance/{event_id}/{player_id}` — AJAX status update. The handler has four non-AJAX fallback `RedirectResponse(f"/attendance/{event_id}", ...)` paths (lines ~184, 194, 203, 213). All four must be updated to redirect to `/events/{event_id}` instead, otherwise form-POST fallbacks (non-JS browsers, failed fetch) will land on a 404.
- `POST /attendance/{event_id}/borrow` — borrow endpoint (no changes needed)

### Update links
Any template that links to `/attendance/{event_id}` is updated to point to `/events/{event_id}` instead. Search all templates for `/attendance/` links.

---

## Data Changes — `event_detail` route (`routes/events.py`)

Two new context variables added to the `event_detail` handler:

**`att_by_player: dict[int, Attendance]`**
Built from a single query with `joinedload(Attendance.borrowed_from_team)`, keyed by `player_id`. Used in the template to look up borrow info per player without N+1 queries.

```python
from sqlalchemy.orm import joinedload
atts = (
    db.query(Attendance)
    .options(joinedload(Attendance.borrowed_from_team))
    .filter(Attendance.event_id == event.id)
    .all()
)
att_by_player = {a.player_id: a for a in atts}
```

**`user_player_ids: set[int]`**
Set of player IDs linked to the current user (`player.user_id == user.id`). Used to gate member editing in the template. Empty set for admins/coaches (they use the existing `is_admin`/`is_coach` check instead).

```python
from models.player import Player
user_player_ids = {
    p.id for p in db.query(Player.id).filter(Player.user_id == user.id).all()
} if not (user.is_admin or user.is_coach) else set()
```

No changes to `get_event_attendance_detail` service function.

---

## Template Changes — `templates/events/detail.html`

### 1. Borrow indicator on player names

In the summary columns, each player `<button>` is currently:
```html
{{ entry.player.full_name }}
```

Change to also show the borrow icon when the player has a borrowed attendance record:
```html
{{ entry.player.full_name }}
{% set att = att_by_player.get(entry.player.id) %}
{% if att and att.borrowed_from_team_id is not none %}
<span class="borrow-icon" tabindex="0">⟳<span class="borrow-tooltip">
  {% if att.borrowed_from_team %}{{ t('attendance.borrow_tooltip', team=att.borrowed_from_team.name) }}{% else %}{{ t('attendance.borrow_tooltip_no_team') }}{% endif %}
</span></span>
{% endif %}
```

### 2. Member editing

Currently the popover (status + note editor) is only rendered for `user.is_admin or (user.is_coach and event.team_id in coach_team_ids)`. Members see the player names but cannot click to edit.

Change: render the popover for **all logged-in users**. In the JS, gate the `openPopover` call:
- Admin/coach: can open popover for any player (existing behavior)
- Member: can open popover only for players whose ID is in `user_player_ids`

Pass `user_player_ids` to the JS as a Set:
```html
var USER_PLAYER_IDS = new Set({{ user_player_ids | list | tojson }});
var IS_PRIVILEGED = {{ 'true' if (user.is_admin or user.is_coach) else 'false' }};
```

In the click handler:
```js
if (!IS_PRIVILEGED && !USER_PLAYER_IDS.has(parseInt(btn.dataset.playerId, 10))) return;
```

The backend already enforces member authorization — this is a UX-only gate.

### 3. Borrow button and dialog

Inside the `{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}` guard, above the attendance columns, add the "Add borrowed player" button:

```html
<div style="margin-bottom:1rem;">
  <button type="button" class="btn btn-outline btn-sm" onclick="openBorrowDialog()">
    + {{ t('attendance.borrow_btn') }}
  </button>
</div>
```

The borrow `<dialog>` markup is moved verbatim. The borrow `<script>` is moved with one adaptation: **`addBorrowRow` must be rewritten** for the column layout. The `mark.html` version targets `<table tbody>`, which does not exist on the detail page. Instead, `addBorrowRow` must append a new `<li class="att-player-item">` containing an `.att-player-btn` to the `unknown` column's `.att-player-list`, matching the existing column structure. It must also call `updateColumn("unknown")` to refresh the count badge.

```js
function addBorrowRow(data) {
  var unknownList = document.querySelector('.att-col[data-bucket="unknown"] .att-player-list');
  if (!unknownList) { location.reload(); return; }

  var tooltipText = data.team_name
    ? _i18n.tooltipTpl.replace('__TEAM__', data.team_name)
    : _i18n.tooltipNoTeam;

  var li = document.createElement('li');
  li.className = 'att-player-item';

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'att-player-btn';
  btn.dataset.playerId = data.player_id;
  btn.dataset.playerName = data.full_name;
  btn.dataset.status = 'unknown';
  btn.dataset.note = '';
  btn.textContent = data.full_name;

  var icon = document.createElement('span');
  icon.className = 'borrow-icon';
  icon.tabIndex = 0;
  icon.textContent = '⟳';
  var tip = document.createElement('span');
  tip.className = 'borrow-tooltip';
  tip.textContent = tooltipText;
  icon.appendChild(tip);
  btn.appendChild(icon);

  li.appendChild(btn);
  unknownList.appendChild(li);
  updateColumn('unknown');
}
```

The borrow JS requires `enums.status` and `event.id` — both already available in the detail page context.

---

## Files Changed

| File | Change |
|---|---|
| `routes/attendance.py` | Remove `GET /{event_id}` handler; update 4 redirect fallbacks in `update_attendance` to `/events/{event_id}` |
| `routes/events.py` | Add `att_by_player` and `user_player_ids` to `event_detail` context |
| `templates/events/detail.html` | Add borrow indicator, member editing gate, borrow button + dialog |
| `templates/attendance/mark.html` | Delete |
| Any template linking to `/attendance/{id}` | Update links to `/events/{id}` |

---

## Testing

- `test_attendance_page` — currently tests `GET /attendance/{id}` returns 200 → update to assert 404 (route deleted)
- `test_mark_attendance_redirects_for_missing_event` — same, update to 404
- `test_attendance_requires_login` — same
- `test_event_detail_includes_att_by_player` — new test: GET `/events/{id}` context includes `att_by_player` dict
- `test_member_can_edit_own_player_from_detail` — new test: member POSTs status update for their own player via `/attendance/{id}/{player_id}`, succeeds
- All existing POST attendance tests remain valid (routes unchanged)
