# Design: Dark/Light Theme Toggle

**Date:** 2026-03-17
**Status:** In Review

## Overview

Add a dark/light theme toggle to ProManager. Pico CSS natively supports `data-theme="dark"` / `data-theme="light"` on `<html>`, so no custom CSS variables are needed. The user's preference is stored in a `theme` cookie so the server can inject the correct `data-theme` before the page renders — eliminating any flash of wrong theme.

The language switcher is moved from the navbar into the user dropdown to reduce navbar clutter. For unauthenticated users, the language switcher moves to the login page footer or is omitted — they can set language after logging in.

## Architecture

### Theme resolution (server-side)

**Resolution order:** `theme` cookie → default `"light"`.

No DB column is added. The cookie is read for **all users** (authenticated and guest). This differs from locale (which prefers the user's DB preference) but is intentional — theme is a display preference stored locally, not a profile setting. Known limitation: clearing cookies resets the theme to light.

Extend `app/middleware/locale.py` to read `request.cookies.get("theme", "light")`, validate it is one of `{"light", "dark"}` (default `"light"` if invalid), and write `request.state.theme`.

### Template

`templates/base.html` `<html>` tag:
```html
<html lang="{{ current_locale }}" data-theme="{{ current_theme }}">
```

`app/templates.py` `render()` injects `current_theme` into every template context (same pattern as `current_locale`).

### User dropdown additions

Inside the existing `<details role="list">` user dropdown, the final structure is:

```
[Register User]  ← admin only (unchanged)
[───────────]    ← hr separator (unchanged)
☀️ Light mode    ← theme toggle link (NEW — shows opposite of current theme)
🌐 Language: [EN ▾]  ← locale select moved from navbar (NEW)
[───────────]    ← new hr separator
[Profile]
[Sign Out]
```

The theme toggle link renders its initial label server-side:
```html
<a href="#" id="theme-toggle-link" onclick="toggleTheme();return false;">
  {% if current_theme == 'dark' %}☀️ Light mode{% else %}🌙 Dark mode{% endif %}
</a>
```

The locale form moves from the navbar `<ul>` into the dropdown as a compact inline select (same `sel-inline` class, same `/set-locale` POST action).

**Unauthenticated users:** The user dropdown is not shown for guests. The language switcher is removed from the navbar. Guests can change language after logging in. Theme toggle is not shown for guests (theme cookie still applies if previously set).

### Client-side theme toggle (inline JS in base.html)

```js
function toggleTheme() {
  const html = document.documentElement;
  const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
  html.dataset.theme = next;
  const secure = location.protocol === 'https:' ? ';secure' : '';
  document.cookie = `theme=${next};max-age=31536000;path=/;samesite=lax${secure}`;
  const link = document.getElementById('theme-toggle-link');
  link.textContent = next === 'dark' ? '☀️ Light mode' : '🌙 Dark mode';
}
```

- `secure` flag is added conditionally based on the current protocol, matching the app's `COOKIE_SECURE` intent without requiring a server round-trip.
- No page reload — instant switch.

### Pre-existing issue noted (out of scope)

`.notif-toast` has a hardcoded `background: #1e293b` that won't adapt to theme. This is a pre-existing issue; fixing it is out of scope for this spec.

## Files to change

| File | Change |
|---|---|
| `app/middleware/locale.py` | Read `theme` cookie, validate, set `request.state.theme` |
| `app/templates.py` | Inject `current_theme` into render context |
| `templates/base.html` | `data-theme` on `<html>`, theme toggle + locale select in user dropdown, remove locale form from navbar |

## Files NOT changed

- No DB migration (no new column)
- No new route (cookie written client-side)
- No new CSS file (Pico CSS handles dark mode natively)
- No new JS file (inline script in base.html)

## Behaviour summary

| Scenario | Result |
|---|---|
| First visit / no cookie | `data-theme="light"` (default) |
| Toggle click | Instant switch, 1-year cookie, no reload |
| Page load with cookie | Server reads cookie → correct `data-theme` in HTML → zero flicker |
| User clears cookies | Resets to light (known limitation, acceptable) |
| HTTPS deployment | Cookie gets `secure` flag automatically |
| Unauthenticated user | Theme applies (cookie), no toggle UI shown |
