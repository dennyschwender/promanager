# Mobile Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all ProManager pages fully usable on mobile — hamburger nav, scrollable tables, and responsive forms.

**Architecture:** CSS-only changes for tables/forms; nav restructure splits the existing second `<ul>` into `#nav-links` (collapsible) and `#user-actions` (always visible), toggled by a small JS function mirroring `toggleTheme()`.

**Tech Stack:** Jinja2 templates, Pico CSS (unprefixed vars), vanilla JS, pytest for regression checks.

---

## Task 1: CSS foundations — `.table-responsive` + hamburger styles + form grid breakpoint

**Files:**
- Modify: `static/css/main.css`

- [ ] **Step 1: Add `.table-responsive` utility class**

Find the `/* ── Misc utilities */` section and add after it:

```css
/* ── Responsive table wrapper ────────────────────────────── */
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

- [ ] **Step 2: Change form grid breakpoint from 480px to 640px**

Find:
```css
@media (max-width: 480px) { .form-grid-2 { grid-template-columns: 1fr; } }
```
Replace with:
```css
@media (max-width: 640px) { .form-grid-2 { grid-template-columns: 1fr; } }
```

- [ ] **Step 3: Add hamburger nav CSS**

At the end of `main.css`, add:

```css
/* ── Mobile navigation ───────────────────────────────────── */
#nav-toggle {
  display: none;
  background: none;
  border: none;
  font-size: 1.3rem;
  cursor: pointer;
  padding: 0.3rem 0.5rem;
  color: var(--color);
  width: auto;
  margin: 0;
}

@media (max-width: 768px) {
  nav.container-fluid {
    position: relative;
  }
  #nav-links {
    display: none;
    flex-direction: column;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 500;
    background: var(--background-color);
    border-bottom: 1px solid var(--muted-border-color);
    padding: 0.5rem 0;
    margin: 0;
    list-style: none;
  }
  #nav-links.open {
    display: flex;
  }
  #nav-links li a {
    display: block;
    padding: 0.55rem 1.25rem;
  }
  #nav-toggle {
    display: inline-flex;
    align-items: center;
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add static/css/main.css
git commit -m "feat: add table-responsive class, hamburger nav CSS, widen form-grid breakpoint to 640px"
```

---

## Task 2: Restructure navbar in base.html

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Read the current nav HTML**

Open `templates/base.html` lines 23–81 to understand the exact current structure before editing.

- [ ] **Step 2: Restructure the nav**

The current nav has:
```html
<nav class="container-fluid">
  <ul>
    <li>...brand...</li>
  </ul>
  <ul>
    {% if user %}
      ...nav links, bell, user dropdown...
    {% else %}
      ...login button...
    {% endif %}
  </ul>
</nav>
```

Replace the second `<ul>` with two separate lists — `#nav-links` for page links and `#user-actions` for user controls + hamburger:

```html
<nav class="container-fluid">
  <ul>
    <li><a href="/dashboard" style="font-weight:700;text-decoration:none;">⬡ ProManager</a></li>
  </ul>
  {% if user %}
  {% set path = request.url.path %}
  <ul id="nav-links">
    <li><a href="/dashboard" class="{% if path == '/dashboard' %}nav-active{% endif %}">{{ t('nav.dashboard') }}</a></li>
    <li><a href="/events"    class="{% if path.startswith('/events') %}nav-active{% endif %}">{{ t('nav.events') }}</a></li>
    <li><a href="/players"   class="{% if path.startswith('/players') %}nav-active{% endif %}">{{ t('nav.players') }}</a></li>
    <li><a href="/teams"     class="{% if path.startswith('/teams') %}nav-active{% endif %}">{{ t('nav.teams') }}</a></li>
    {% if user.is_admin %}
      <li><a href="/seasons"  class="{% if path.startswith('/seasons') %}nav-active{% endif %}">{{ t('nav.seasons') }}</a></li>
      <li><a href="/reports"  class="{% if path.startswith('/reports') %}nav-active{% endif %}">{{ t('nav.reports') }}</a></li>
    {% endif %}
  </ul>
  <ul id="user-actions">
    <li>
      <a href="/notifications" class="notif-bell" title="{{ t('nav.notifications') }}" aria-label="{{ t('nav.notifications') }}">
        🔔
        {% if request.state.unread_count > 0 %}
          <span class="notif-badge">{{ request.state.unread_count }}</span>
        {% endif %}
      </a>
    </li>
    <li>
      <details role="list" style="list-style:none;">
        <summary aria-haspopup="listbox" role="link">{{ user.username }}</summary>
        <ul role="listbox" style="right:0;left:auto;">
          {% if user.is_admin %}
            <li><a href="/auth/register">{{ t('nav.register_user') }}</a></li>
            <li><hr style="margin:.25rem 0;"></li>
          {% endif %}
          <li><a href="/profile">{{ t('nav.profile') }}</a></li>
          <li>
            <a href="#" data-theme-toggle onclick="toggleTheme(); return false;">
              {% if current_theme == 'dark' %}☀️ {{ t('nav.light_mode') }}{% else %}🌙 {{ t('nav.dark_mode') }}{% endif %}
            </a>
          </li>
          <li>
            <form method="post" action="/set-locale" style="display:flex;align-items:center;gap:.3rem;margin:0;padding:.25rem 1rem;">
              <input type="hidden" name="next" value="{{ request.url.path }}">
              <span style="font-size:.9rem;">🌐</span>
              <select name="locale" onchange="this.form.submit()" class="sel-inline">
                <option value="en" {% if current_locale == 'en' %}selected{% endif %}>EN</option>
                <option value="it" {% if current_locale == 'it' %}selected{% endif %}>IT</option>
                <option value="fr" {% if current_locale == 'fr' %}selected{% endif %}>FR</option>
                <option value="de" {% if current_locale == 'de' %}selected{% endif %}>DE</option>
              </select>
            </form>
          </li>
          <li><hr style="margin:.25rem 0;"></li>
          <li><a href="/auth/logout">{{ t('nav.sign_out') }}</a></li>
        </ul>
      </details>
    </li>
    <li>
      <button id="nav-toggle" aria-label="Toggle navigation" aria-expanded="false"
              onclick="toggleMenu()">☰</button>
    </li>
  </ul>
  {% else %}
  <ul id="user-actions">
    <li><a href="/auth/login" role="button" class="outline">{{ t('nav.login') }}</a></li>
  </ul>
  {% endif %}
</nav>
```

- [ ] **Step 3: Add `toggleMenu()` JS**

Find the existing `<script>` block containing `toggleTheme()` and add `toggleMenu()` alongside it:

```js
function toggleMenu() {
  const menu = document.getElementById('nav-links');
  const btn = document.getElementById('nav-toggle');
  if (!menu) return;
  const isOpen = menu.classList.toggle('open');
  btn.setAttribute('aria-expanded', isOpen);
  btn.textContent = isOpen ? '✕' : '☰';
}
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('#nav-links a').forEach(function(link) {
    link.addEventListener('click', function() {
      const menu = document.getElementById('nav-links');
      const btn = document.getElementById('nav-toggle');
      if (!menu) return;
      menu.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = '☰';
    });
  });
});
```

- [ ] **Step 4: Run tests — verify nav renders without template errors**

```bash
source .venv/bin/activate && pytest tests/test_auth.py tests/test_dashboard.py -v --tb=short 2>&1 | tail -20
```

These tests render pages that include `base.html`. Expected: all pass. A Jinja2 template error will show as a 500 / exception in the test output.

Then run the full suite:
```bash
pytest -v --tb=short 2>&1 | tail -20
```

Expected: same pass/fail count as before (2 known failures in `test_import.py` only).

- [ ] **Step 5: Commit**

```bash
git add templates/base.html
git commit -m "feat: hamburger nav — split nav-links / user-actions, add toggleMenu()"
```

---

## Task 3: Wrap tables in teams, seasons, events

**Files:**
- Modify: `templates/teams/list.html`
- Modify: `templates/seasons/list.html`
- Modify: `templates/events/list.html`

For each file: find `<table` and wrap it in `<div class="table-responsive">...</div>`.

- [ ] **Step 1: `teams/list.html`**

Find `<table` in the file, wrap it:
```html
<div class="table-responsive">
  <table ...>
    ...
  </table>
</div>
```

- [ ] **Step 2: `seasons/list.html`**

Same pattern — wrap the single `<table>`.

- [ ] **Step 3: `events/list.html` — two tables**

There are two separate tables (upcoming events and past events). Wrap each one independently with `<div class="table-responsive">`.

- [ ] **Step 4: Commit**

```bash
git add templates/teams/list.html templates/seasons/list.html templates/events/list.html
git commit -m "feat: wrap teams/seasons/events tables in table-responsive"
```

---

## Task 4: Wrap tables in attendance, reports, dashboard, import

**Files:**
- Modify: `templates/attendance/mark.html`
- Modify: `templates/reports/season.html`
- Modify: `templates/reports/player.html`
- Modify: `templates/dashboard/index.html`
- Modify: `templates/players/import.html`

- [ ] **Step 1: `attendance/mark.html`**

Find the admin `<table>` (the one showing all players for admin attendance marking) and wrap it:
```html
<div class="table-responsive">
  <table ...>...</table>
</div>
```

- [ ] **Step 2: `reports/season.html`**

Wrap the single report table.

- [ ] **Step 3: `reports/player.html`**

Wrap the single report table.

- [ ] **Step 4: `dashboard/index.html`**

Wrap the "Next 5 Events" table.

- [ ] **Step 5: `players/import.html`**

Find the skipped-rows results table (shown after a failed import). Wrap it. Also check if there are any additional bare tables in this file and wrap them too.

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
git add templates/attendance/mark.html templates/reports/season.html templates/reports/player.html templates/dashboard/index.html templates/players/import.html
git commit -m "feat: wrap attendance/reports/dashboard/import tables in table-responsive"
```

---

## Task 5: flex-wrap fix on teams/detail.html

**Files:**
- Modify: `templates/teams/detail.html`

- [ ] **Step 1: Fix button group**

Find the action button div near the top of the page content:
```html
style="display:flex;gap:.5rem;"
```
Change to:
```html
style="display:flex;gap:.5rem;flex-wrap:wrap;"
```

- [ ] **Step 2: Commit**

```bash
git add templates/teams/detail.html
git commit -m "fix: add flex-wrap to teams detail action buttons"
```

---

## Task 6: Final verification and push

- [ ] **Step 1: Run full test suite**

```bash
source .venv/bin/activate && pytest -v --tb=short 2>&1 | tail -30
```

Expected: same pass/fail count as before (2 known failures in `test_import.py` only).

- [ ] **Step 2: Manual mobile check (if server available)**

Start server: `source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 7000`

Check in browser DevTools at 375px width (iPhone SE):
1. Navbar: nav links hidden, ☰ visible → opens dropdown on click → closes on link click
2. `/teams` — table scrolls horizontally
3. `/seasons` — table scrolls horizontally
4. `/events` — both tables scroll horizontally
5. `/players/new` — form inputs stack to single column
6. `/dashboard` — events table scrolls horizontally

- [ ] **Step 3: Push**

```bash
git push
```
