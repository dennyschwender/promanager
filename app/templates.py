"""app/templates.py — Shared Jinja2Templates instance.

Import `templates` from here instead of instantiating Jinja2Templates
in each route module. This ensures globals (now, urlencode) are available
in every rendered template.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.filters["urlencode"] = quote_plus
