"""app/templates.py — Shared Jinja2Templates instance and render() helper.

Import `templates` from here instead of instantiating Jinja2Templates
in each route module. This ensures globals (now, urlencode) are available
in every rendered template.

Use render() to get t() and current_locale automatically injected.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import DEFAULT_LOCALE
from app.i18n import t as _t

def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "0"


from app.config import settings as _settings  # noqa: PLC0415

templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.globals["static_v"] = _git_rev()
templates.env.globals["app_name"] = _settings.APP_NAME
templates.env.filters["urlencode"] = quote_plus


def render(
    request: Request,
    template_name: str,
    context: dict,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a template with i18n context (t, current_locale) auto-injected."""
    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    theme = getattr(request.state, "theme", "light")

    def _te(key: str) -> str:
        return _t(f"enums.{key}", locale)

    # Lookup dicts for DB enum values → translated labels
    enums = {
        "event_type": {v: _te(f"event_type_{v}") for v in ("training", "match", "other")},
        "status": {v: _te(f"status_{v}") for v in ("attend", "absent", "unknown", "maybe")},
        "role": {v: _te(f"role_{v}") for v in ("admin", "member", "player", "coach", "assistant", "team_leader")},
        "position": {v: _te(f"pos_{v}") for v in ("goalie", "defender", "center", "forward")},
        "sex": {v: _te(f"sex_{v}") for v in ("male", "female", "other")},
        "recurrence": {v: _te(f"recurrence_{v}") for v in ("weekly", "biweekly", "monthly")},
        "membership_status": {v: _te(f"membership_{v}") for v in ("active", "inactive", "injured")},
    }

    i18n_ctx = {
        "t": lambda key, **kw: _t(key, locale, **kw),
        "current_locale": locale,
        "current_theme": theme,
        "enums": enums,
    }
    return templates.TemplateResponse(
        request,
        template_name,
        {**i18n_ctx, **context},
        status_code=status_code,
    )
