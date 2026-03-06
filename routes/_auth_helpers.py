"""routes/_auth_helpers.py — FastAPI auth guard dependencies."""

from __future__ import annotations

from fastapi import Request

from models.user import User

# ---------------------------------------------------------------------------
# Custom exceptions — handled in app/main.py with proper HTML responses
# ---------------------------------------------------------------------------


class NotAuthenticated(Exception):
    """Raised when a route requires login but no session is present."""


class NotAuthorized(Exception):
    """Raised when a route requires admin but the user is not one."""


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def require_login(request: Request) -> User:
    """Return the current user or raise NotAuthenticated.

    Usage::

        @router.get("/foo")
        async def foo(user: User = Depends(require_login)):
            ...
    """
    user = request.state.user
    if user is None:
        raise NotAuthenticated()
    return user


def require_admin(request: Request) -> User:
    """Return the current admin user or raise NotAuthenticated / NotAuthorized.

    Usage::

        @router.post("/admin/action")
        async def action(user: User = Depends(require_admin)):
            ...
    """
    user: User = require_login(request)
    if not user.is_admin:
        raise NotAuthorized()
    return user
