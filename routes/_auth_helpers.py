"""routes/_auth_helpers.py — FastAPI auth guard dependencies."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session as _Session

from app.i18n import DEFAULT_LOCALE
from app.i18n import t as _i18n_t
from models.user import User
from models.user_team import UserTeam as _UserTeam

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


def optional_user(request: Request) -> "User | None":
    """Return the current user or None (no redirect). For public routes that adapt to auth state."""
    return request.state.user


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


# ---------------------------------------------------------------------------
# Coach / team-scoped helpers
# ---------------------------------------------------------------------------


def get_coach_teams(
    user: User,
    db: _Session,
    season_id: int | None = None,
) -> set[int]:
    """Return set of team_ids the coach manages (optionally scoped to a season).

    season_id=None → return all assigned teams regardless of season.
    season_id=X   → return teams assigned for season X OR with no season scope (NULL).
    Always returns empty set for non-coach users; callers should check is_admin first.
    """
    q = db.query(_UserTeam.team_id).filter(_UserTeam.user_id == user.id)
    if season_id:
        q = q.filter(or_(_UserTeam.season_id == season_id, _UserTeam.season_id.is_(None)))
    return {row[0] for row in q.all()}


def check_team_access(
    user: User,
    team_id: int,
    db: _Session,
    season_id: int | None = None,
) -> None:
    """Raise NotAuthorized if the user cannot manage the given team.

    Admins always pass. Coaches pass only if a matching UserTeam row exists.
    Pass season_id to enforce season-scoped assignments.
    """
    if user.is_admin:
        return
    if team_id not in get_coach_teams(user, db, season_id=season_id):
        raise NotAuthorized


def require_coach_or_admin(request: Request, user: User = Depends(require_login)) -> User:
    """FastAPI dependency: allows admins and coaches only."""
    if not (user.is_admin or user.is_coach):
        raise NotAuthorized
    return user


def rt(request: Request, key: str, **kwargs) -> str:
    """Translate a key using the current request locale."""
    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    return _i18n_t(key, locale, **kwargs)
