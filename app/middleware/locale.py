"""app/middleware/locale.py — Resolves the active locale for each request.

Resolution order:
  1. Logged-in user: request.state.user.locale
  2. Guest: 'locale' cookie
  3. Default: 'en'

Sets request.state.locale.

Registration order in app/main.py (LIFO — last added runs first):
  app.add_middleware(LocaleMiddleware)  # added first → runs second
  app.add_middleware(AuthMiddleware)   # added second → runs first
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.i18n import SUPPORTED_LOCALES


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        locale = "en"

        # 1. Authenticated user preference
        user = getattr(request.state, "user", None)
        if user is not None:
            user_locale = getattr(user, "locale", None)
            if user_locale and user_locale in SUPPORTED_LOCALES:
                locale = user_locale

        # 2. Cookie fallback — only for unauthenticated users.
        # Authenticated users always use their DB locale (even if it is "en").
        # To change locale, authenticated users must POST to /set-locale.
        if locale == "en" and user is None:
            cookie_locale = request.cookies.get("locale", "")
            if cookie_locale in SUPPORTED_LOCALES:
                locale = cookie_locale

        request.state.locale = locale
        return await call_next(request)
