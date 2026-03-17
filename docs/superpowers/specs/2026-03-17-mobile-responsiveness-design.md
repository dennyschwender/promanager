# Mobile Responsiveness — Design Spec

**Date:** 2026-03-17
**Status:** Approved

## Context

ProManager is used by coaches and managers on the go. Currently the app has several mobile UX problems: the navbar overflows on small screens, most tables lack horizontal scroll wrappers causing layout breakage, and form grids collapse too late (480px) leaving cramped two-column layouts on tablets.

## Goals

- Navigation usable on all screen sizes via hamburger dropdown
- All tables scrollable horizontally on small screens
- Forms stack to single column at 640px and below
- No hardcoded widths or layouts breaking on < 768px screens

---

## 1. Navigation — Hamburger Dropdown

**Files:** `templates/base.html`, `static/css/main.css`

### HTML Restructure

The current nav has two `<ul>` elements (brand, then everything mixed). Split the second into two:

```html
<nav class="container-fluid">
  <ul>
    <li><a href="/dashboard" ...>⬡ ProManager</a></li>
  </ul>
  <ul id="nav-links">
    <!-- page nav links: Dashboard, Events, Players, Teams, Seasons, Reports, bell -->
    <!-- (only rendered when user is logged in) -->
  </ul>
  <ul id="user-actions">
    <!-- login button (guests) OR user dropdown (authenticated) -->
    <li>
      <button id="nav-toggle" aria-label="Toggle navigation" aria-expanded="false"
              onclick="toggleMenu()">☰</button>
    </li>
  </ul>
</nav>
```

- `#nav-links` — page nav links + notification bell; hidden on mobile
- `#user-actions` — always visible; contains login button or username dropdown + hamburger `<button>`
- `#nav-toggle` — hidden on desktop via CSS, visible on mobile

### CSS

```css
/* Desktop: hamburger hidden */
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
  #nav-links {
    display: none;                  /* hidden by default on mobile */
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
  nav.container-fluid {
    position: relative;             /* anchor for absolute #nav-links */
  }
}
```

### JavaScript

```js
function toggleMenu() {
  const menu = document.getElementById('nav-links');
  const btn = document.getElementById('nav-toggle');
  const isOpen = menu.classList.toggle('open');
  btn.setAttribute('aria-expanded', isOpen);
  btn.textContent = isOpen ? '✕' : '☰';
}
// Close menu when a nav link is clicked
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('#nav-links a').forEach(function(link) {
    link.addEventListener('click', function() {
      document.getElementById('nav-links').classList.remove('open');
      const btn = document.getElementById('nav-toggle');
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = '☰';
    });
  });
});
```

Added before `</body>` alongside `toggleTheme()`.

---

## 2. Tables — Horizontal Scroll Wrappers

**Files:** `static/css/main.css` + 8 templates

### CSS

```css
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

### Templates — wrap each `<table>` in `<div class="table-responsive">`

| Template | Tables to wrap |
|---|---|
| `templates/teams/list.html` | 1 (teams table) |
| `templates/seasons/list.html` | 1 (seasons table) |
| `templates/events/list.html` | 2 (upcoming + past events) |
| `templates/attendance/mark.html` | 1 (admin attendance table) |
| `templates/reports/season.html` | 1 (season report table) |
| `templates/reports/player.html` | 1 (player report table) |
| `templates/dashboard/index.html` | 1 (next 5 events table) |
| `templates/players/import.html` | 1 (skipped rows results table) |

Tables already wrapped with inline `overflow-x:auto` style (no action needed): `players/list.html`, `players/detail.html`. During implementation, verify `players/import.html` for any additional tables beyond the skipped-rows result table.

---

## 3. Form Grid Breakpoint

**File:** `static/css/main.css`

Change:
```css
@media (max-width: 480px) { .form-grid-2 { grid-template-columns: 1fr; } }
```
To:
```css
@media (max-width: 640px) { .form-grid-2 { grid-template-columns: 1fr; } }
```

Templates that use `.form-grid-2` and benefit from this change:
- `templates/players/form.html` — multiple `.form-grid-2` sections
- `templates/events/form.html` — multiple `.form-grid-2` sections

`templates/teams/form.html` uses `.form-container-wide` but not `.form-grid-2` — unaffected.

---

## 4. Minor Flex-Wrap Fix

**`templates/teams/detail.html`** — action button group at top of page:

Current: `style="display:flex;gap:.5rem;"`
Fix: `style="display:flex;gap:.5rem;flex-wrap:wrap;"`

(`templates/notifications/inbox.html` already has `flex-wrap:wrap` — no change needed.)

---

## Files Modified

- `static/css/main.css`
- `templates/base.html`
- `templates/teams/list.html`
- `templates/seasons/list.html`
- `templates/events/list.html`
- `templates/attendance/mark.html`
- `templates/reports/season.html`
- `templates/reports/player.html`
- `templates/dashboard/index.html`
- `templates/players/import.html`
- `templates/teams/detail.html`

---

## Verification

1. Open app on a 375px-wide viewport (Chrome DevTools → iPhone SE simulation)
2. **Navbar**: nav links hidden, ☰ visible → click opens vertical dropdown; clicking a link closes it; ✕ shown when open
3. **Tables**: scroll all tables horizontally — no page overflow, content accessible
4. **Forms**: `players/form`, `events/form` — all inputs stack to single column at ≤ 640px
5. **Teams detail**: action buttons wrap to second line when narrow
6. Run `pytest -v` — confirm no regressions
