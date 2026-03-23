# Merge Attendance Page into Event Detail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the standalone `/attendance/{event_id}` page and absorb all its functionality into the event detail page (`/events/{event_id}`).

**Architecture:** The event detail route gains two new context variables (`att_by_player`, `user_player_ids`). The detail template gains the borrow button/dialog (with an adapted `addBorrowRow` for the column layout) and member editing capability. The attendance GET route and template are deleted; its four non-AJAX redirect fallbacks are updated to point to `/events/{event_id}`. Two nav links in other templates are updated.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2 templates, Pico CSS, vanilla JS

---

## File Map

| File | Change |
|---|---|
| `routes/attendance.py` | Delete `GET /{event_id}` handler; update 4 redirect fallbacks in `update_attendance` to `/events/{event_id}` |
| `routes/events.py` | Add `att_by_player` + `user_player_ids` to `event_detail` context |
| `templates/events/detail.html` | Add borrow indicator, member editing gate, borrow button + dialog with adapted `addBorrowRow` |
| `templates/attendance/mark.html` | Delete |
| `templates/dashboard/index.html` | Update `/attendance/{{ event.id }}` link to `/events/{{ event.id }}` |
| `templates/events/list.html` | Update `/attendance/{{ e.id }}` link to `/events/{{ e.id }}` |
| `tests/test_attendance.py` | Update 3 GET tests that test the now-deleted route |

---

## Task 1: Update tests for the deleted GET route

**Files:**
- Modify: `tests/test_attendance.py`

The three GET tests at the top of the file currently assert that `GET /attendance/{id}` works. After Task 2, that route is gone (404). Update the tests now so they reflect the new expected behavior, then watch them fail until Task 2 is complete.

- [ ] **Step 1: Update the three GET tests**

Open `tests/test_attendance.py`. Replace the three tests under `# Attendance page (GET)`:

```python
# ---------------------------------------------------------------------------
# Attendance page (GET) — route removed, now returns 404
# ---------------------------------------------------------------------------


def test_attendance_page_no_longer_exists(admin_client, db):
    """GET /attendance/{id} returns 404 after route deletion."""
    event = _make_event(db)
    resp = admin_client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 404


def test_attendance_missing_event_no_longer_exists(admin_client):
    """GET /attendance/99999 returns 404 after route deletion."""
    resp = admin_client.get("/attendance/99999", follow_redirects=False)
    assert resp.status_code == 404


def test_attendance_login_redirect_no_longer_exists(client, db):
    """GET /attendance/{id} returns 404 (route gone, not a login redirect)."""
    event = _make_event(db, title="Auth Test Event")
    resp = client.get(f"/attendance/{event.id}", follow_redirects=False)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the three updated tests — expect FAIL**

```bash
cd /home/denny/Development/promanager && source .venv/bin/activate && pytest tests/test_attendance.py::test_attendance_page_no_longer_exists tests/test_attendance.py::test_attendance_missing_event_no_longer_exists tests/test_attendance.py::test_attendance_login_redirect_no_longer_exists -v
```

Expected: FAIL (route still exists, returns 200/302 not 404).

- [ ] **Step 3: Commit**

```bash
git add tests/test_attendance.py
git commit -m "test: update GET attendance tests to expect 404 after route deletion"
```

---

## Task 2: Delete the GET route and update redirect fallbacks

**Files:**
- Modify: `routes/attendance.py`

- [ ] **Step 1: Delete the `attendance_page` handler**

Remove the entire `GET /{event_id}` handler (lines 28–91 in `routes/attendance.py`), including the section comment above it:

```python
# ---------------------------------------------------------------------------
# Attendance marking page
# ---------------------------------------------------------------------------


@router.get("/{event_id}")
async def attendance_page(
    ...
):
    ...
```

Delete everything from `# Attendance marking page` down to (but not including) `# Borrow a player for a single event`.

Also remove these imports that are now only used by the deleted handler (check first that nothing else in the file uses them):
- `from app.templates import render` — check if used elsewhere; if not, remove
- `get_event_attendance_summary` from `services.attendance_service` — check if used elsewhere; if not, remove
- `joinedload` from `sqlalchemy.orm` — used only in `attendance_page`; remove after deleting that handler

- [ ] **Step 2: Update the 4 redirect fallbacks in `update_attendance`**

In `update_attendance` (the `POST /{event_id}/{player_id}` handler), find all four `RedirectResponse(f"/attendance/{event_id}", ...)` lines and change them to `/events/{event_id}`:

Line ~184 (invalid status fallback):
```python
return RedirectResponse(f"/events/{event_id}", status_code=302)
```

Line ~194 (coach event not found fallback):
```python
return RedirectResponse(f"/events/{event_id}", status_code=302)
```

Line ~203 (member unauthorized fallback):
```python
return RedirectResponse(f"/events/{event_id}", status_code=302)
```

Line ~213 (success redirect with flash):
```python
flash_msg = quote(rt(request, "common.changes_saved"))
return RedirectResponse(f"/events/{event_id}?flash={flash_msg}", status_code=302)
```

Note: the flash query param goes to the events detail page — which already reads `request.query_params.get("flash")` (add it to the detail context in Task 3 if not already there).

- [ ] **Step 3: Run the three updated tests — expect PASS now**

```bash
pytest tests/test_attendance.py::test_attendance_page_no_longer_exists tests/test_attendance.py::test_attendance_missing_event_no_longer_exists tests/test_attendance.py::test_attendance_login_redirect_no_longer_exists -v
```

Expected: all 3 PASS.

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. If any test hits `/attendance/{id}` GET and breaks, update it.

- [ ] **Step 5: Commit**

```bash
git add routes/attendance.py
git commit -m "feat: remove GET /attendance/{id} route and redirect fallbacks to /events/{id}"
```

---

## Task 3: Enhance `event_detail` route with new context

**Files:**
- Modify: `routes/events.py`

- [ ] **Step 1: Add imports**

At the top of `routes/events.py`, check if these are already imported; add any that are missing:

```python
from sqlalchemy.orm import joinedload
from models.attendance import Attendance
from models.player import Player
```

- [ ] **Step 2: Update the `event_detail` handler**

Find `event_detail` (around line 404). Replace its body with:

```python
@router.get("/{event_id}")
async def event_detail(
    event_id: int,
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    summary = get_event_attendance_detail(db, event_id)

    future_count = (
        count_future_events(db, event.recurrence_group_id)
        if event.recurrence_group_id
        else 0
    )

    atts = (
        db.query(Attendance)
        .options(joinedload(Attendance.borrowed_from_team))
        .filter(Attendance.event_id == event_id)
        .all()
    )
    att_by_player = {a.player_id: a for a in atts}

    # For members: which of their players are linked to this user
    if not (user.is_admin or user.is_coach):
        user_player_ids = {
            p.id
            for p in db.query(Player).filter(
                Player.user_id == user.id,
                Player.archived_at.is_(None),
            ).all()
        }
    else:
        user_player_ids = set()

    return render(
        request,
        "events/detail.html",
        {
            "user": user,
            "event": event,
            "summary": summary,
            "coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
            "future_count": future_count,
            "att_by_player": att_by_player,
            "user_player_ids": user_player_ids,
            "flash": request.query_params.get("flash"),
        },
    )
```

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add routes/events.py
git commit -m "feat: add att_by_player and user_player_ids to event_detail context"
```

---

## Task 3b: Write new tests for the enhanced event detail route

**Files:**
- Modify: `tests/test_events.py`

Add these two tests at the bottom of `tests/test_events.py`. They verify the new context variables added in Task 3.

- [ ] **Step 1: Add the two new tests**

```python
def test_event_detail_includes_att_by_player(admin_client, db):
    """GET /events/{id} context provides att_by_player keyed by player_id."""
    from models.attendance import Attendance
    from models.player import Player

    event = Event(title="Context Test", event_type="training", event_date=date.today())
    db.add(event)
    db.commit()
    db.refresh(event)

    player = Player(first_name="Test", last_name="Player", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)

    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()

    resp = admin_client.get(f"/events/{event.id}", follow_redirects=False)
    assert resp.status_code == 200


def test_member_can_edit_own_player_from_detail(client, db):
    """A member can POST attendance for their own player via /attendance/{id}/{player_id}."""
    from models.attendance import Attendance
    from models.player import Player
    from services.auth_service import create_session_cookie, create_user

    member = create_user(db, "member_detail", "detail@test.com", "password1", role="member")
    event = Event(title="Member Edit Event", event_type="training", event_date=date.today())
    db.add(event)
    db.commit()
    db.refresh(event)

    player = Player(first_name="Own", last_name="Player", is_active=True, user_id=member.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    db.add(Attendance(event_id=event.id, player_id=player.id, status="unknown"))
    db.commit()

    client.cookies.set("session_user_id", create_session_cookie(member.id))
    resp = client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "present", "note": ""},
        follow_redirects=False,
    )
    # Should redirect to /events/{id} (not /attendance/{id})
    assert resp.status_code == 302
    assert f"/events/{event.id}" in resp.headers["location"]

    att = db.query(Attendance).filter(
        Attendance.event_id == event.id, Attendance.player_id == player.id
    ).first()
    assert att is not None
    assert att.status == "present"
```

- [ ] **Step 2: Run the two new tests**

```bash
cd /home/denny/Development/promanager && source .venv/bin/activate && pytest tests/test_events.py::test_event_detail_includes_att_by_player tests/test_events.py::test_member_can_edit_own_player_from_detail -v
```

Expected:
- `test_event_detail_includes_att_by_player` — PASS (route already returns 200; this is a smoke test)
- `test_member_can_edit_own_player_from_detail` — PASS after Task 2 (redirect now goes to `/events/{id}`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_events.py
git commit -m "test: add event detail att_by_player and member edit redirect tests"
```

---

## Task 4: Update the two nav links

**Files:**
- Modify: `templates/dashboard/index.html`
- Modify: `templates/events/list.html`

- [ ] **Step 1: Update `templates/dashboard/index.html`**

Find (around line 36):
```html
<td><a href="/attendance/{{ event.id }}" class="btn btn-sm btn-primary">{{ t('events.attendance') }}</a></td>
```

Replace with:
```html
<td><a href="/events/{{ event.id }}" class="btn btn-sm btn-primary">{{ t('events.attendance') }}</a></td>
```

- [ ] **Step 2: Update `templates/events/list.html`**

Find (around line 62):
```html
<a href="/attendance/{{ e.id }}">{{ t('events.attendance') }}</a>
```

Replace with:
```html
<a href="/events/{{ e.id }}">{{ t('events.attendance') }}</a>
```

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard/index.html templates/events/list.html
git commit -m "fix: update attendance nav links from /attendance/{id} to /events/{id}"
```

---

## Task 5: Update `detail.html` — borrow indicator + member editing + borrow dialog

**Files:**
- Modify: `templates/events/detail.html`

This is the largest task. Read `templates/events/detail.html` in full before making any changes.

### Step 1: Add borrow indicator to player buttons

Find the player button in the attendance columns (around line 103):

```html
            {{ entry.player.full_name }}
```

Replace with:

```html
            {{ entry.player.full_name }}
            {% set att = att_by_player.get(entry.player.id) %}
            {% if att and att.borrowed_from_team_id is not none %}
            <span class="borrow-icon" tabindex="0">⟳<span class="borrow-tooltip">
              {% if att.borrowed_from_team %}{{ t('attendance.borrow_tooltip', team=att.borrowed_from_team.name) }}{% else %}{{ t('attendance.borrow_tooltip_no_team') }}{% endif %}
            </span></span>
            {% endif %}
```

- [ ] **Step 1: Apply the borrow indicator change above**

### Step 2: Extend popover to members and add flash display

The popover is currently inside `{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}`. Members need it too.

Move the popover and its `<script>` block **outside** that guard so it renders for all logged-in users (the JS will gate who can open it).

In the JS, add two variables right after `var EVENT_ID = {{ event.id }};`:

```js
var USER_PLAYER_IDS = new Set({{ user_player_ids | list | tojson }});
var IS_PRIVILEGED = {{ 'true' if (user.is_admin or (user.is_coach and event.team_id in coach_team_ids)) else 'false' }};
```

In the `openPopover` call inside the click handler (around line 229), add a guard at the top of the handler:

```js
document.getElementById('attendance-columns').addEventListener('click', function (e) {
    var btn = e.target.closest('.att-player-btn');
    if (!btn) return;
    var pid = parseInt(btn.dataset.playerId, 10);
    if (!IS_PRIVILEGED && !USER_PLAYER_IDS.has(pid)) return;
    e.stopPropagation();
    openPopover(btn);
});
```

Also add flash display just after the action bar (after line 68, before the `{% if request.query_params... %}` block):

```html
{% if flash %}
  <div class="alert alert-success">{{ flash }}</div>
{% endif %}
```

(Check if flash is already displayed — if so, skip this step.)

- [ ] **Step 2: Apply member editing + flash changes above**

### Step 3: Add "Add borrowed player" button

Inside `{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}`, before `<h3>{{ t('events.attendance_summary') }}</h3>` (or right before the `att-columns` div), add:

```html
  <div style="margin-bottom:1rem;">
    <button type="button" class="btn btn-outline btn-sm" onclick="openBorrowDialog()">
      + {{ t('attendance.borrow_btn') }}
    </button>
  </div>
```

- [ ] **Step 3: Apply borrow button change above**

### Step 4: Add borrow dialog and adapted JS

At the end of `{% block content %}`, before the delete dialog block, add the borrow dialog and script.

The `<dialog>` markup is identical to `mark.html`. The script is the same **except** `addBorrowRow` is replaced with the column-aware version below.

```html
{# ── Borrow dialog ───────────────────────────────────────────── #}
{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}
<dialog id="borrow-dialog" class="att-dialog">
  <article>
    <header>
      <h3>{{ t('attendance.borrow_title') }}</h3>
    </header>
    <input type="text" id="borrow-search-input"
           placeholder="{{ t('attendance.borrow_search_placeholder') }}"
           autocomplete="off">
    <div id="borrow-results" style="margin-top:.5rem;max-height:200px;overflow-y:auto;"></div>
    <p id="borrow-error" style="color:var(--tp-danger,#c0392b);display:none;margin-top:.5rem;"></p>
    <footer class="att-dialog-actions">
      <button type="button" class="btn btn-outline"
              onclick="document.getElementById('borrow-dialog').close()">
        {{ t('common.cancel') }}
      </button>
      <button type="button" class="btn btn-primary" id="borrow-add-btn" disabled
              onclick="submitBorrow()">
        {{ t('attendance.borrow_add') }}
      </button>
    </footer>
  </article>
</dialog>

<script>
(function() {
  var _sel = null;
  var _debounce = null;
  var _csrf = '{{ request.state.csrf_token }}';
  var _eventId = {{ event.id }};
  var _i18n = {
    noTeam: {{ t('attendance.borrow_no_team') | tojson }},
    tooltipTpl: {{ t('attendance.borrow_tooltip', team='__TEAM__') | tojson }},
    tooltipNoTeam: {{ t('attendance.borrow_tooltip_no_team') | tojson }},
    errDuplicate: {{ t('attendance.borrow_err_duplicate') | tojson }},
    errNotFound: {{ t('attendance.borrow_err_not_found') | tojson }},
    errEventNotFound: {{ t('attendance.borrow_err_event_not_found') | tojson }},
    errGeneric: {{ t('attendance.borrow_err_generic') | tojson }}
  };

  window.openBorrowDialog = function() {
    _sel = null;
    document.getElementById('borrow-search-input').value = '';
    document.getElementById('borrow-results').textContent = '';
    document.getElementById('borrow-error').style.display = 'none';
    document.getElementById('borrow-add-btn').disabled = true;
    document.getElementById('borrow-dialog').showModal();
    setTimeout(function() { document.getElementById('borrow-search-input').focus(); }, 50);
  };

  document.getElementById('borrow-search-input').addEventListener('input', function() {
    clearTimeout(_debounce);
    var q = this.value;
    _debounce = setTimeout(function() { doSearch(q); }, 300);
  });

  function doSearch(q) {
    var container = document.getElementById('borrow-results');
    container.textContent = '';
    if (q.length < 2) return;
    fetch('/players/search?q=' + encodeURIComponent(q) + '&exclude_event_id=' + _eventId)
      .then(function(r) { return r.json(); })
      .then(function(players) {
        if (!players.length) {
          var p = document.createElement('p');
          p.className = 'text-muted';
          p.style.padding = '.4rem .6rem';
          p.textContent = 'No results';
          container.appendChild(p);
          return;
        }
        players.forEach(function(player) {
          var row = document.createElement('div');
          row.className = 'borrow-result';
          row.style.cssText = 'padding:.4rem .6rem;cursor:pointer;border-radius:4px;';
          var strong = document.createElement('strong');
          strong.textContent = player.full_name;
          row.appendChild(strong);
          var muted = document.createElement('span');
          muted.className = 'text-muted';
          muted.textContent = ' — ' + (player.team_name || _i18n.noTeam);
          row.appendChild(muted);
          row.addEventListener('click', function() {
            document.querySelectorAll('.borrow-result').forEach(function(r) { r.style.background = ''; });
            row.style.background = 'var(--primary-focus, rgba(0,0,0,.1))';
            _sel = { id: player.id, fullName: player.full_name, teamName: player.team_name };
            document.getElementById('borrow-add-btn').disabled = false;
            document.getElementById('borrow-error').style.display = 'none';
          });
          container.appendChild(row);
        });
      });
  }

  window.submitBorrow = function() {
    if (!_sel) return;
    var form = new FormData();
    form.append('player_id', _sel.id);
    form.append('csrf_token', _csrf);
    fetch('/attendance/' + _eventId + '/borrow', { method: 'POST', body: form })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.ok) {
          document.getElementById('borrow-dialog').close();
          addBorrowRow(data);
        } else {
          var msg = data.error === 'already_attending' ? _i18n.errDuplicate
                  : data.error === 'player_not_found' ? _i18n.errNotFound
                  : data.error === 'event_not_found' ? _i18n.errEventNotFound
                  : _i18n.errGeneric;
          var errEl = document.getElementById('borrow-error');
          errEl.textContent = msg;
          errEl.style.display = 'block';
        }
      })
      .catch(function() {
        var errEl = document.getElementById('borrow-error');
        errEl.textContent = _i18n.errGeneric;
        errEl.style.display = 'block';
      });
  };

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
})();
</script>
{% endif %}
```

- [ ] **Step 4: Apply the borrow dialog + script above**

### Step 5: Run the full test suite

```bash
cd /home/denny/Development/promanager && source .venv/bin/activate && pytest -v
```

Expected: all tests pass.

### Step 6: Commit

```bash
git add templates/events/detail.html
git commit -m "feat: add borrow indicator, member editing, and borrow dialog to event detail page"
```

---

## Task 6: Delete `templates/attendance/mark.html`

**Files:**
- Delete: `templates/attendance/mark.html`

- [ ] **Step 1: Delete the template file**

```bash
rm /home/denny/Development/promanager/templates/attendance/mark.html
```

- [ ] **Step 2: Run full test suite and lint**

```bash
cd /home/denny/Development/promanager && source .venv/bin/activate && pytest -v && ruff check . && ruff format .
```

Expected: all tests pass, no lint errors.

- [ ] **Step 3: Commit and push**

```bash
git add -A
git commit -m "feat: delete attendance mark template — fully merged into event detail"
git push
```

---

## Notes for implementers

- `get_event_attendance_detail` (imported in `routes/events.py`) returns `{bucket: [{player, note}]}` — `entry.player` is the Player ORM object. The `att_by_player` dict keyed by `player_id` lets the template look up the matching Attendance row for borrow info.
- The popover JS already has `movePlayer` and `updateColumn` functions — `addBorrowRow` in the borrow script calls `updateColumn('unknown')` which relies on these being in scope. They are in the same `<script>` block on the page, so this works fine.
- `enums.status` is globally injected into all templates via `app/templates.py` — no need to pass it explicitly.
- The `flash` query param is now read in `event_detail` and passed to the template. Verify the template already has `{% if flash %}<div class="alert alert-success">{{ flash }}</div>{% endif %}` — if not, add it near the top of `{% block content %}`.
