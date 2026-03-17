# Dark/Light Theme Toggle Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dark/light theme toggle to ProManager using Pico CSS's native `data-theme` attribute, stored in a cookie for zero-flicker SSR, with the toggle and language switcher both living in the user dropdown.

**Architecture:** `LocaleMiddleware` is extended to also read the `theme` cookie and set `request.state.theme`. `app/templates.py` `render()` injects `current_theme` into every template. `base.html` sets `data-theme` on `<html>` and adds a JS-powered toggle link + locale select inside the user dropdown.

**Tech Stack:** FastAPI, Starlette middleware, Jinja2, Pico CSS (`data-theme`), vanilla JS, HTTP cookies.

**Spec:** `docs/superpowers/specs/2026-03-17-dark-light-theme-design.md`

---

## Chunk 1: Middleware + render() + tests

### Task 1: Extend LocaleMiddleware to resolve theme

**Files:**
- Modify: `app/middleware/locale.py`
- Test: `tests/test_theme_middleware.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_theme_middleware.py`:

```python
"""Tests for theme resolution in LocaleMiddleware."""
from __future__ import annotations


def test_theme_defaults_to_light(client):
    """No cookie → data-theme="light" in rendered HTML."""
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert 'data-theme="light"' in resp.text


def test_theme_cookie_dark(client):
    """theme=dark cookie → data-theme="dark"."""
    client.cookies.set("theme", "dark")
    resp = client.get("/auth/login")
    assert 'data-theme="dark"' in resp.text


def test_theme_cookie_invalid_defaults_to_light(client):
    """Invalid theme cookie value falls back to light."""
    client.cookies.set("theme", "purple")
    resp = client.get("/auth/login")
    assert 'data-theme="light"' in resp.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/denny/Development/promanager
source .venv/bin/activate
pytest tests/test_theme_middleware.py -v
```

Expected: FAIL — `data-theme` attribute not present in HTML yet.

- [ ] **Step 3: Extend LocaleMiddleware**

In `app/middleware/locale.py`, add theme resolution after the existing locale logic:

```python
SUPPORTED_THEMES = {"light", "dark"}

class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # ... existing locale logic unchanged ...

        # Theme: cookie → default "light" (for all users)
        raw_theme = request.cookies.get("theme", "light")
        request.state.theme = raw_theme if raw_theme in SUPPORTED_THEMES else "light"

        return await call_next(request)
```

Add `SUPPORTED_THEMES = {"light", "dark"}` at module level, before the class.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_theme_middleware.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add app/middleware/locale.py tests/test_theme_middleware.py
git commit -m "feat: resolve theme cookie in LocaleMiddleware"
```

---

### Task 2: Inject current_theme into render() context

**Files:**
- Modify: `app/templates.py`

- [ ] **Step 1: Update render()**

In `app/templates.py`, extend `render()` to inject `current_theme`:

```python
def render(
    request: Request,
    template_name: str,
    context: dict,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a template with i18n and theme context auto-injected."""
    locale = getattr(request.state, "locale", "en")
    theme = getattr(request.state, "theme", "light")
    i18n_ctx = {
        "t": lambda key, **kw: _t(key, locale, **kw),
        "current_locale": locale,
        "current_theme": theme,
    }
    return templates.TemplateResponse(
        request,
        template_name,
        {**i18n_ctx, **context},
        status_code=status_code,
    )
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

```bash
pytest -v --tb=short
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/templates.py
git commit -m "feat: inject current_theme into render() context"
```

---

## Chunk 2: base.html — data-theme + user dropdown

### Task 3: Set data-theme on <html> and add toggle + locale to dropdown

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Update `<html>` tag**

Change line 2 of `templates/base.html` from:
```html
<html lang="{{ current_locale }}">
```
to:
```html
<html lang="{{ current_locale }}" data-theme="{{ current_theme }}">
```

- [ ] **Step 2: Add theme toggle + locale select to user dropdown**

Locate the `<ul role="listbox">` inside the `<details>` dropdown (currently around line 50). Replace its contents with:

```html
<ul role="listbox">
  {% if user.is_admin %}
    <li><a href="/auth/register">{{ t('nav.register_user') }}</a></li>
    <li><hr style="margin:.25rem 0;"></li>
  {% endif %}
  <li>
    <a href="#" id="theme-toggle-link" onclick="toggleTheme();return false;">
      {% if current_theme == 'dark' %}☀️ Light mode{% else %}🌙 Dark mode{% endif %}
    </a>
  </li>
  <li>
    <form method="post" action="/set-locale" style="margin:0;">
      <input type="hidden" name="next" value="{{ request.url.path }}">
      <select name="locale" onchange="this.form.submit()" class="sel-inline" style="width:100%;">
        <option value="en" {% if current_locale == 'en' %}selected{% endif %}>🌐 EN</option>
        <option value="it" {% if current_locale == 'it' %}selected{% endif %}>🌐 IT</option>
        <option value="fr" {% if current_locale == 'fr' %}selected{% endif %}>🌐 FR</option>
        <option value="de" {% if current_locale == 'de' %}selected{% endif %}>🌐 DE</option>
      </select>
    </form>
  </li>
  <li><hr style="margin:.25rem 0;"></li>
  <li><a href="/profile">{{ t('nav.profile') }}</a></li>
  <li><a href="/auth/logout">{{ t('nav.sign_out') }}</a></li>
</ul>
```

- [ ] **Step 3: Remove the locale form from the navbar**

Delete the `<li>` block in the navbar `<ul>` that contains the locale `<form>` with the `🌐` emoji and `sel-inline` select (the block starting around line 62). The entire `<li>...</li>` wrapping that form should be removed.

- [ ] **Step 4: Add toggleTheme() JS function**

Add this inline script to `base.html` just before `</body>` (after the existing scripts):

```html
<script>
function toggleTheme() {
  const html = document.documentElement;
  const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
  html.dataset.theme = next;
  const secure = location.protocol === 'https:' ? ';secure' : '';
  document.cookie = 'theme=' + next + ';max-age=31536000;path=/;samesite=lax' + secure;
  const link = document.getElementById('theme-toggle-link');
  link.textContent = next === 'dark' ? '☀️ Light mode' : '🌙 Dark mode';
}
</script>
```

- [ ] **Step 5: Manual verification**

Start the dev server and verify:
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 7000
```

- Visit http://localhost:7000/auth/login — page should load without flicker in light mode
- Log in; open the user dropdown — "🌙 Dark mode" link and language select should appear; old globe form should be gone from navbar
- Click "🌙 Dark mode" — page instantly switches to dark; link changes to "☀️ Light mode"
- Reload — stays dark (cookie persists)
- Click "☀️ Light mode" — switches back to light

- [ ] **Step 6: Run full test suite**

```bash
pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add templates/base.html
git commit -m "feat: dark/light theme toggle in user dropdown; move locale select into dropdown"
```

---

## Chunk 3: Final commit + push

- [ ] **Push to remote**

```bash
git push
```

- [ ] **Deploy to pi4desk (optional — user decision)**

```bash
ssh pi4desk "cd ~/dockerimages/proManager && git pull && docker compose up -d --build"
```
