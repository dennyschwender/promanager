"""app/templates.py — Shared Jinja2Templates instance and render() helper.

Import `templates` from here instead of instantiating Jinja2Templates
in each route module. This ensures globals (now, urlencode) are available
in every rendered template.

Use render() to get t() and current_locale automatically injected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import DEFAULT_LOCALE
from app.i18n import t as _t

templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
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
