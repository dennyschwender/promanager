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

**File:** `templates/base.html`, `static/css/main.css`

On screens ≤ 768px:
- Hide the `<ul>` containing page nav links (Dashboard, Events, Players, Teams, Seasons, Reports)
- Show a `☰` hamburger `<button id="nav-toggle">` in the top-right area of the navbar
- The user section (bell + username dropdown) remains always visible
- Clicking ☰ toggles `<ul id="nav-menu">` open/closed as a vertical dropdown panel below the navbar, full width, with each link on its own row

**JS:** Small `toggleMenu()` function added before `</body>`, same pattern as `toggleTheme()`.

**CSS additions:**
```css
@media (max-width: 768px) {
  #nav-links { display: none; }
  #nav-toggle { display: inline-flex; }
  #nav-menu.open { display: flex; flex-direction: column; ... }
}
#nav-toggle { display: none; } /* hidden on desktop */
```

---

## 2. Tables — Horizontal Scroll Wrappers

**File:** `static/css/main.css` + 8 templates

Add to `main.css`:
```css
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

Wrap every bare `<table>` that lacks a scroll container:

| Template | Tables to wrap |
|---|---|
| `teams/list.html` | 1 (teams table) |
| `seasons/list.html` | 1 (seasons table) |
| `events/list.html` | 2 (upcoming + past events) |
| `attendance/mark.html` | 1 (admin attendance table) |
| `reports/season.html` | 1 (season report table) |
| `reports/player.html` | 1 (player report table) |
| `dashboard/index.html` | 1 (next 5 events table) |
| `players/import.html` | 1 (skipped rows results table) |

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

This affects: `players/form.html`, `events/form.html`, `teams/form.html` — all use `.form-grid-2`.

---

## 4. Minor Flex-Wrap Fixes

**`templates/teams/detail.html`** — button group at top of page:
- Add `flex-wrap: wrap` to the `style="display:flex;gap:.5rem;"` container

**`templates/notifications/inbox.html`** — mark-all-read form:
- Add `flex-wrap: wrap` to its inline form container

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
- `templates/notifications/inbox.html`

---

## Verification

1. Open app on a 375px-wide viewport (Chrome DevTools mobile simulation)
2. Navbar: nav links hidden, ☰ button visible → click opens dropdown with all nav links
3. Tables: all tables scroll horizontally without breaking page layout
4. Forms: players/form, events/form, teams/form — all inputs stack to single column at ≤ 640px
5. Teams detail: action buttons wrap to second line when narrow
6. Run `pytest -v` — no regressions
