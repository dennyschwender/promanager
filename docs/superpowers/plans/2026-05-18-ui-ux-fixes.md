# UI/UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix all 19 UI/UX issues found during full-site audit, ordered by severity (Critical → Major → Medium → Minor).

**Architecture:** Pure CSS + Jinja2 template fixes — no backend changes needed. Badge contrast uses explicit hex colors. Mobile layout uses media query overrides. Destructive-action safety uses the existing `.action-dropdown` pattern already in events/list.html.

**Tech Stack:** FastAPI/Jinja2, PicoCSS, custom `static/css/main.css`, pytest + `tests/` suite, Chrome browser automation via mcp__claude-in-chrome

---

## File Map

| File | Tasks |
|------|-------|
| `static/css/main.css` | T1, T5, T6, T7 |
| `templates/base.html` | T4, T10 |
| `templates/players/list.html` | T1, T3 |
| `templates/events/detail.html` | T2, T9, T13 |
| `templates/events/list.html` | T11 |
| `templates/seasons/list.html` | T8 |
| `templates/teams/list.html` | T8 |
| `templates/reports/season.html` | T14 |
| `templates/auth/profile.html` | T15 |
| `locales/en.json` | T11, T12 |
| `locales/de.json` | T12 |
| `locales/fr.json` | T12 |
| `locales/it.json` | T12 |

---

## CRITICAL

### Task 1: Fix white-on-white button text in light mode

Root cause: PicoCSS sets `button { color: var(--color) }` which resolves to `#fff` for all buttons. Plain/transparent buttons (`#nav-toggle`, `.tab-btn`) become invisible in light mode.

**Files:**
- Modify: `static/css/main.css:763`
- Modify: `templates/players/list.html` (tab-btn inline styles)

- [x] **Step 1: Fix `#nav-toggle` color in main.css**

In `static/css/main.css`, change line 763:
```css
/* FROM: */
  color: var(--color);
/* TO: */
  color: inherit;
```

The full `#nav-toggle` block (lines 756–766) becomes:
```css
#nav-toggle {
  display: none;
  background: none;
  border: none;
  font-size: 1.3rem;
  cursor: pointer;
  padding: 0.3rem 0.5rem;
  color: inherit;
  width: auto;
  margin: 0;
}
```

- [x] **Step 2: Fix tab-btn color in players/list.html**

In `templates/players/list.html`, find the tab button inline styles (around lines 26–36). Each button has `style="border:none;background:none;..."`. Add `color:inherit` to each button's inline style.

Read the file first to get exact line numbers, then change every occurrence of the tab button `style` attribute from:
```html
style="border:none;background:none;padding:.3rem .75rem;cursor:pointer;..."
```
to:
```html
style="border:none;background:none;color:inherit;padding:.3rem .75rem;cursor:pointer;..."
```

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "player" 2>&1 | tail -20
```
Expected: all player tests pass.

- [x] **Step 4: Verify in Chrome — light mode, both pages**

Open http://localhost:7000/players in light mode. Check:
- Tab buttons (All / Active / Inactive / No User) are visible (dark text)
- Hamburger ☰ button is visible on mobile viewport (≤768px)

- [x] **Step 5: Commit**

```bash
git add static/css/main.css templates/players/list.html
git commit -m "fix: white-on-white button text in light mode (nav-toggle + tab-btn)"
```

---

## MAJOR

### Task 2: Fix lineup panel mobile overflow

At ≤480px, `.lineup-groups-col` has `display:flex;flex-wrap:wrap` with groups having `flex:1;min-width:130px`. Two groups still fit side-by-side (~50% each > 130px), so they don't stack.

**Files:**
- Modify: `templates/events/detail.html` (inline `<style>` in lineup panel section, around lines 792–860)

- [x] **Step 1: Read the lineup style block**

```bash
source .venv/bin/activate && python -c "
with open('templates/events/detail.html') as f:
    lines = f.readlines()
for i, l in enumerate(lines, 1):
    if 'lineup-workspace' in l or 'lineup-groups-col' in l or '480px' in l:
        print(i, l, end='')
"
```

- [x] **Step 2: Update the media query for lineup**

In `templates/events/detail.html`, find the `@media(max-width:480px)` block that contains lineup styles. Change it so groups stack vertically:

```css
@media(max-width:480px){
  .lineup-workspace{flex-direction:column;}
  .lineup-pool-col{flex:none;width:100%;}
  .lineup-groups-col{width:100%;flex-direction:column;}
  .lineup-group{flex:1 1 100%;min-width:unset;}
}
```

The only additions vs current are `flex-direction:column` on `.lineup-groups-col` and `flex:1 1 100%;min-width:unset` on `.lineup-group`.

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "event" 2>&1 | tail -20
```
Expected: all event tests pass.

- [x] **Step 4: Verify in Chrome at 375px width**

Open any event detail page with a lineup. Resize browser to 375px wide. Check:
- Lineup groups stack vertically (one per row, full width)
- No horizontal scroll on the lineup panel

- [x] **Step 5: Commit**

```bash
git add templates/events/detail.html
git commit -m "fix: lineup groups stack vertically on mobile (≤480px)"
```

---

### Task 3: Hide secondary columns in Members table on mobile

Too many columns visible on small screens in `templates/players/list.html`. Phone, Date of birth, Active, Has User are non-essential on mobile.

**Files:**
- Modify: `templates/players/list.html` (table thead `<th>` and tbody `<td>`)

- [x] **Step 1: Read the players table**

Read `templates/players/list.html` and identify lines with `Phone`, `date_of_birth`, `is_active`, `has_user` column headers and their corresponding `<td>` cells.

- [x] **Step 2: Add `col-hide-mobile` class to secondary columns**

For each secondary column, add `class="col-hide-mobile"` to both the `<th>` header and every `<td>` cell in that column.

Secondary columns to hide on mobile: Phone, Date of Birth, Active, Has User (keep: Name, Team, Position, Actions).

Example pattern — change:
```html
<th>{{ t('players.phone') }}</th>
```
to:
```html
<th class="col-hide-mobile">{{ t('players.phone') }}</th>
```

And the corresponding `<td>`:
```html
<td class="col-hide-mobile">{{ p.phone or '—' }}</td>
```

Repeat for all four secondary columns.

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "player" 2>&1 | tail -20
```
Expected: all player tests pass.

- [x] **Step 4: Verify in Chrome at 375px**

Open http://localhost:7000/players at 375px width. Check:
- Only essential columns visible (Name, Team/Position, Actions)
- No horizontal scroll on the members table

- [x] **Step 5: Commit**

```bash
git add templates/players/list.html
git commit -m "fix: hide secondary player columns on mobile"
```

---

## MEDIUM

### Task 4: Fix notification bell badge clipping

`.notif-badge` uses `top: -6px; right: -8px` relative to `.notif-bell`. If the parent nav clips overflow, the badge gets cut off.

**Files:**
- Modify: `templates/base.html` (inline `<style>` block, lines 22–28)

- [x] **Step 1: Update notif-bell to allow overflow**

In `templates/base.html`, change the `.notif-bell` inline style from:
```css
.notif-bell { position: relative; text-decoration: none; font-size: 1.1rem; }
```
to:
```css
.notif-bell { position: relative; text-decoration: none; font-size: 1.1rem; overflow: visible; }
```

Also adjust badge offset for better visual placement — change:
```css
.notif-badge {
    position: absolute; top: -6px; right: -8px;
```
to:
```css
.notif-badge {
    position: absolute; top: -8px; right: -10px;
```

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```
Expected: all tests pass.

- [x] **Step 3: Verify in Chrome — both themes, both sizes**

Navigate to any page with unread notifications. Check:
- Badge number fully visible at desktop and mobile
- Badge not clipped by nav bar edges in light and dark themes

- [x] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "fix: notification badge overflow clipping in nav"
```

---

### Task 5: Improve stat card contrast in light mode

Stat cards currently blend with the page background in light mode. Adding a left accent border gives visual anchoring.

**Files:**
- Modify: `static/css/main.css:173–180` (`.stat-card` block)

- [x] **Step 1: Add left accent border to stat-card**

In `static/css/main.css`, change `.stat-card` from:
```css
.stat-card {
  background: var(--card-background-color, #fff);
  border: 1px solid var(--muted-border-color, #e0e0e0);
  border-radius: var(--tp-radius);
  padding: 0.6rem 0.75rem;
  text-align: center;
  box-shadow: var(--tp-shadow);
}
```
to:
```css
.stat-card {
  background: var(--card-background-color, #fff);
  border: 1px solid var(--muted-border-color, #e0e0e0);
  border-left: 3px solid var(--tp-primary);
  border-radius: var(--tp-radius);
  padding: 0.6rem 0.75rem;
  text-align: center;
  box-shadow: var(--tp-shadow);
}
```

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```

- [x] **Step 3: Verify in Chrome — light mode dashboard**

Open http://localhost:7000/dashboard in light mode. Check:
- Stat cards have a distinct blue left border
- Cards visually separated from page background
- Looks correct in dark mode too (border uses `--tp-primary` which adapts)

- [x] **Step 4: Commit**

```bash
git add static/css/main.css
git commit -m "fix: stat card visual contrast — add primary accent border"
```

---

### Task 6: Fix low-contrast badges (training + unknown)

`.badge-training` and `.badge-unknown` use `background: #e8e8e8; color: var(--tp-muted)` where `--tp-muted: #6c757d`. Contrast ratio ≈ 3.1:1, below WCAG AA 4.5:1.

**Files:**
- Modify: `static/css/main.css:205–208`

- [x] **Step 1: Update badge colors**

In `static/css/main.css`, change lines 205 and 208:
```css
/* FROM: */
.badge-unknown  { background: #e8e8e8; color: var(--tp-muted); }
.badge-training { background: #e8e8e8; color: var(--tp-muted); }

/* TO: */
.badge-unknown  { background: #e2e3e5; color: #41464b; }
.badge-training { background: #e2e3e5; color: #41464b; }
```

`#41464b` on `#e2e3e5` = contrast ratio ~5.9:1 (WCAG AA pass).

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```

- [x] **Step 3: Verify in Chrome — light mode event list**

Open http://localhost:7000/events in light mode. Check:
- "Training" badges are clearly readable
- "Unknown" attendance badges are clearly readable

- [x] **Step 4: Commit**

```bash
git add static/css/main.css
git commit -m "fix: badge-unknown and badge-training contrast ratio (WCAG AA)"
```

---

### Task 7: Move Delete button to dropdown on Seasons and Teams pages

Delete button is currently inline alongside non-destructive actions. It should be separated to prevent accidental clicks. Use the existing `.action-dropdown` pattern from events/list.html.

**Files:**
- Modify: `templates/seasons/list.html:26–42`
- Modify: `templates/teams/list.html:24–43`

- [x] **Step 1: Update seasons/list.html**

In `templates/seasons/list.html`, replace the `<div class="action-group">` block (lines 26–42) with an action-dropdown pattern:

```html
<td>
  <div class="action-dropdown">
    <button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">⋯</button>
    <div class="action-dropdown-menu">
      {% if user.is_admin %}
        <a href="/seasons/{{ s.id }}/edit">{{ t('seasons.edit') }}</a>
        {% if not s.is_active %}
          <form method="post" action="/seasons/{{ s.id }}/activate" style="display:contents;">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" class="dropdown-item-btn">{{ t('seasons.activate') }}</button>
          </form>
        {% endif %}
        <a href="/reports/season/{{ s.id }}">{{ t('seasons.report') }}</a>
        <form method="post" action="/seasons/{{ s.id }}/delete" style="display:contents;"
              onsubmit="return confirm('{{ t('seasons.delete_confirm', name=s.name) }}')">
          <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
          <button type="submit" class="dropdown-item-btn dropdown-item-danger">{{ t('common.delete') }}</button>
        </form>
      {% endif %}
    </div>
  </div>
</td>
```

- [x] **Step 2: Update teams/list.html**

In `templates/teams/list.html`, replace the `<div class="action-group">` block (lines 24–43) with:

```html
<td>
  <div class="action-dropdown">
    <button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">⋯</button>
    <div class="action-dropdown-menu">
      <a href="/teams/{{ team.id }}/edit">{{ t('teams.edit') }}</a>
      <a href="/players?team_id={{ team.id }}">{{ t('teams.players') }}</a>
      {% if user.is_admin %}
        <a href="/players/import?team_id={{ team.id }}">{{ t('common.import') }}</a>
        {% if seasons|length > 1 %}
        <button type="button" class="dropdown-item-btn"
                data-team-id="{{ team.id }}" data-team-name="{{ team.name | e }}"
                onclick="openCopyDialog(this)">
          {{ t('teams_list.copy_roster') }}
        </button>
        {% endif %}
        <form method="post" action="/teams/{{ team.id }}/delete" style="display:contents;"
              onsubmit="return confirm('{{ t('teams_list.delete_confirm', name=team.name) }}')">
          <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
          <button type="submit" class="dropdown-item-btn dropdown-item-danger">{{ t('common.delete') }}</button>
        </form>
      {% endif %}
    </div>
  </div>
</td>
```

- [x] **Step 3: Add dropdown-item-btn and dropdown-item-danger styles to main.css**

Check if `.dropdown-item-btn` is already defined in `static/css/main.css`. If not, add after the existing `.action-dropdown-menu a` rules:

```css
.dropdown-item-btn {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  padding: 0.4rem 0.85rem;
  font-size: .88rem;
  cursor: pointer;
  color: inherit;
  border-radius: .25rem;
}
.dropdown-item-btn:hover { background: var(--tp-surface, #f4f4f4); }
.dropdown-item-danger { color: var(--tp-danger, #c0392b) !important; }
```

Also add the dropdown JS to both templates `{% block scripts %}` — or verify the existing dropdown JS from base.html/events/list.html is already global. If the JS is page-local (only in events/list.html), add the dropdown toggle script to `base.html` instead, or include it in seasons/list.html and teams/list.html.

The JS needed (check if already in base.html or a global script):
```javascript
document.addEventListener('click', function (e) {
  var toggle = e.target.closest('.action-dropdown-toggle');
  if (toggle) {
    e.stopPropagation();
    var menu = toggle.nextElementSibling;
    var isOpen = menu.classList.contains('open');
    document.querySelectorAll('.action-dropdown-menu.open').forEach(m => m.classList.remove('open', 'open-up'));
    if (!isOpen) {
      menu.classList.add('open');
      var rect = toggle.getBoundingClientRect();
      if (window.innerHeight - rect.bottom < 120) menu.classList.add('open-up');
    }
    return;
  }
  document.querySelectorAll('.action-dropdown-menu.open').forEach(m => m.classList.remove('open', 'open-up'));
});
```

- [x] **Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "season or team" 2>&1 | tail -20
```
Expected: all season and team tests pass.

- [x] **Step 5: Verify in Chrome**

Open http://localhost:7000/seasons and http://localhost:7000/teams. Check:
- Delete button no longer directly visible
- Clicking ⋯ opens dropdown containing all actions including Delete (in red)
- Delete still shows confirm dialog before submitting

- [x] **Step 6: Commit**

```bash
git add templates/seasons/list.html templates/teams/list.html static/css/main.css
git commit -m "fix: move delete action into dropdown on seasons and teams pages"
```

---

### Task 8: Fix lineup chip text alignment

`.lineup-chip` uses `justify-content:space-between` but without a remove button visible in pool view, the player name gets pushed to the right side of the chip.

**Files:**
- Modify: `templates/events/detail.html` (inline `<style>`, `.lineup-chip` rule)

- [x] **Step 1: Find and fix `.lineup-chip` style**

In `templates/events/detail.html`, find the `.lineup-chip` CSS rule. Change:
```css
.lineup-chip { ... justify-content:space-between; ... }
```
to:
```css
.lineup-chip { ... justify-content:flex-start; gap:.4rem; ... }
```

If the rule already uses `gap` for the remove button spacing, keep it. If not present, add `gap:.4rem` to ensure the name and any action button still have spacing.

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "event" 2>&1 | tail -10
```

- [x] **Step 3: Verify in Chrome**

Open an event detail page with lineup configured. Check:
- Player names in chips are left-aligned
- Remove button (×) still accessible at right side if it exists

- [x] **Step 4: Commit**

```bash
git add templates/events/detail.html
git commit -m "fix: lineup chip player names left-aligned"
```

---

## MINOR

### Task 9: Add missing footer links (Teams + Reports)

Footer only has Dashboard, All Events, Members, Seasons — missing Teams and Reports.

**Files:**
- Modify: `templates/base.html` (footer section, around lines 127–140)

- [x] **Step 1: Read the footer section**

Read `templates/base.html` lines 125–145 to see current footer links.

- [x] **Step 2: Add Teams and Reports links**

In the footer, add Teams and Reports links conditional on user role (same conditions as nav). After the existing Members/Seasons links, add:

```html
{% if user and (user.is_admin or user.is_coach) %}
<li><a href="/teams">{{ t('nav.teams') }}</a></li>
{% endif %}
{% if user %}
<li><a href="/reports">{{ t('nav.reports') }}</a></li>
{% endif %}
```

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```

- [x] **Step 4: Verify in Chrome**

Open any page as admin. Scroll to footer. Check:
- Teams and Reports links present
- Links work correctly

- [x] **Step 5: Commit**

```bash
git add templates/base.html
git commit -m "fix: add Teams and Reports links to footer"
```

---

### Task 10: Fix cryptic "✓/n" attendance column header

The `✓/n` column header in the events table is cryptic. Replace with a proper label using a translation key.

**Files:**
- Modify: `templates/events/list.html:59`
- Modify: `locales/en.json`
- Modify: `locales/de.json`
- Modify: `locales/fr.json`
- Modify: `locales/it.json`

- [x] **Step 1: Add translation key to locales**

In `locales/en.json`, find the `"events"` section and add:
```json
"att_summary": "Att."
```

In `locales/de.json`, add to `"events"` section:
```json
"att_summary": "Teiln."
```

In `locales/fr.json`, add to `"events"` section:
```json
"att_summary": "Prés."
```

In `locales/it.json`, add to `"events"` section:
```json
"att_summary": "Pres."
```

- [x] **Step 2: Update the template**

In `templates/events/list.html`, change line 59:
```html
<th class="col-nowrap col-hide-mobile">✓/n</th>
```
to:
```html
<th class="col-nowrap col-hide-mobile" title="{{ t('reports.attendance_rate') }}">{{ t('events.att_summary') }}</th>
```

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "event" 2>&1 | tail -10
```

- [x] **Step 4: Verify in Chrome**

Open http://localhost:7000/events. Check:
- Column header shows "Att." (not ✓/n)
- Hovering shows tooltip "Attendance Rate"

- [x] **Step 5: Commit**

```bash
git add templates/events/list.html locales/en.json locales/de.json locales/fr.json locales/it.json
git commit -m "fix: replace cryptic ✓/n column header with translated Att. label"
```

---

### Task 11: Fix "All attendee" typo in locale files

`events_detail.pt_all` and `events_form.pt_all` contain "All attendee" (missing 's'). Lines 664 and 702 in `locales/en.json`.

**Files:**
- Modify: `locales/en.json`

- [x] **Step 1: Fix the typo**

In `locales/en.json`, change both occurrences of `"All attendee"` to `"All attendees"`:
- Line 664: `"pt_all": "All attendee"` → `"pt_all": "All attendees"`
- Line 702: `"pt_all": "All attendee"` → `"pt_all": "All attendees"`

Note: line 601 says `"pt_all": "All"` which is in a different section and is correct — do not change it.

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -10
```

- [x] **Step 3: Verify in Chrome**

Open event form (create or edit). Check presence type dropdown shows "All attendees" (not "All attendee").

- [x] **Step 4: Commit**

```bash
git add locales/en.json
git commit -m "fix: typo All attendee → All attendees in en.json"
```

---

### Task 12: Add aria-label/tooltip to ⋯ action button on event detail

The `⋯` three-dots button has no accessible label or tooltip.

**Files:**
- Modify: `templates/events/detail.html` (around lines 72–74, the `⋯` button)

- [x] **Step 1: Find the ⋯ button**

Read `templates/events/detail.html` around lines 70–80 to find the exact button markup.

- [x] **Step 2: Add aria-label and title**

Change the `⋯` button from:
```html
<button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">⋯</button>
```
to:
```html
<button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true" aria-label="{{ t('common.more_actions') }}" title="{{ t('common.more_actions') }}">⋯</button>
```

Also add `"more_actions": "More actions"` to the `"common"` section of `locales/en.json` (and equivalent in de/fr/it).

In `locales/en.json` → `"common"` section: `"more_actions": "More actions"`
In `locales/de.json` → `"common"` section: `"more_actions": "Weitere Aktionen"`
In `locales/fr.json` → `"common"` section: `"more_actions": "Plus d'actions"`
In `locales/it.json` → `"common"` section: `"more_actions": "Altre azioni"`

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "event" 2>&1 | tail -10
```

- [x] **Step 4: Verify in Chrome**

Open any event detail page. Hover over ⋯ button. Check tooltip appears with "More actions".

- [x] **Step 5: Commit**

```bash
git add templates/events/detail.html locales/en.json locales/de.json locales/fr.json locales/it.json
git commit -m "fix: add aria-label and title to event detail more-actions button"
```

---

### Task 13: Fix season chip overflow on mobile in reports

Season switcher buttons in reports use full-width layout on mobile, causing overflow.

**Files:**
- Modify: `templates/reports/season.html:22–29`

- [x] **Step 1: Wrap season switcher in a scrollable container**

In `templates/reports/season.html`, change the season switcher row (lines 22–29) from:
```html
<div class="filter-row" style="margin-bottom:.5rem;">
  <span style="font-size:.85rem;color:var(--muted-color);align-self:flex-end;">{{ t('reports.seasons_label') }}</span>
  {% for s in all_seasons %}
    ...season links...
  {% endfor %}
</div>
```
to:
```html
<div style="margin-bottom:.5rem;overflow-x:auto;white-space:nowrap;-webkit-overflow-scrolling:touch;">
  <span style="font-size:.85rem;color:var(--muted-color);margin-right:.5rem;">{{ t('reports.seasons_label') }}</span>
  {% for s in all_seasons %}
    {% set qs = season_qs() %}
    <a href="/reports/season/{{ s.id }}{% if qs %}?{{ qs }}{% endif %}"
       class="btn btn-sm {% if s.id == season.id %}btn-primary{% else %}btn-outline{% endif %}" style="white-space:nowrap;">{{ s.name }}</a>
  {% endfor %}
</div>
```

- [x] **Step 2: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "report" 2>&1 | tail -10
```

- [x] **Step 3: Verify in Chrome at 375px**

Open http://localhost:7000/reports/season/1 at 375px width. Check:
- Season buttons scrollable horizontally without causing page overflow
- Active season button still highlighted

- [x] **Step 4: Commit**

```bash
git add templates/reports/season.html
git commit -m "fix: season switcher chips horizontally scrollable on mobile"
```

---

### Task 14: Improve profile page section visual separation

Profile page sections (`Notifications`, `Language`, `Password`, `Sessions`) lack visual separation — no card/border around each section.

**Files:**
- Modify: `templates/auth/profile.html`

- [x] **Step 1: Read profile.html**

Read `templates/auth/profile.html` to find section structure.

- [x] **Step 2: Wrap each section in an article element**

For each `<section>` or `<div>` grouping a profile block, wrap it in `<article>` (PicoCSS styles `<article>` with background + border + padding automatically):

Replace each bare section like:
```html
<h3>{{ t('profile.notifications_title') }}</h3>
<p>...</p>
<button ...>...</button>
```
with:
```html
<article>
  <h3>{{ t('profile.notifications_title') }}</h3>
  <p>...</p>
  <button ...>...</button>
</article>
```

Apply to all major profile sections.

- [x] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -v -k "profile or auth" 2>&1 | tail -10
```

- [x] **Step 4: Verify in Chrome — both themes**

Open http://localhost:7000/profile. Check:
- Each section has a visually distinct card background/border
- Looks clean in both light and dark modes

- [x] **Step 5: Commit**

```bash
git add templates/auth/profile.html
git commit -m "fix: wrap profile sections in article cards for visual separation"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] T1: White-on-white buttons (nav-toggle + tab-btn) — Critical
- [x] T2: Lineup mobile overflow — Major
- [x] T3: Members table mobile columns — Major
- [x] T4: Notification bell badge clipping — Medium
- [x] T5: Stat card light mode contrast — Medium
- [x] T6: badge-training + badge-unknown contrast — Medium
- [x] T7: Delete button safety (seasons + teams) — Medium
- [x] T8: Lineup chip alignment — Medium
- [x] T9: Footer missing links — Minor
- [x] T10: Cryptic ✓/n column header — Minor
- [x] T11: "All attendee" typo — Minor
- [x] T12: ⋯ button tooltip — Minor
- [x] T13: Season chip mobile overflow — Minor
- [x] T14: Profile section card styling — Minor

All 19 originally found issues covered (some consolidated: badge contrast covers both training+unknown; delete covers both seasons+teams).
