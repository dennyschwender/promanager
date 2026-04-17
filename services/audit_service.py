"""services/audit_service.py — Append-only audit log helper."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import Request

logger = logging.getLogger(__name__)


def log_action(
    action: str,
    *,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    target_label: str | None = None,
    extra: dict | None = None,
    ip_address: str | None = None,
    request: Request | None = None,
) -> None:
    """Append one row to audit_log. Opens its own DB session — safe to call anywhere.

    If request is provided, actor and IP are extracted automatically (can be
    overridden by explicit keyword args).
    """
    if request is not None:
        if actor_user_id is None and request.state.user is not None:
            actor_user_id = request.state.user.id
        if actor_username is None and request.state.user is not None:
            actor_username = request.state.user.username
        if ip_address is None:
            # Handle X-Forwarded-For for reverse proxies
            forwarded = request.headers.get("x-forwarded-for")
            ip_address = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None

    try:
        import app.database as _db_mod  # noqa: PLC0415
        from models.audit_log import AuditLog  # noqa: PLC0415

        db = _db_mod.SessionLocal()
        try:
            row = AuditLog(
                created_at=datetime.now(timezone.utc),
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_label=target_label,
                extra=json.dumps(extra) if extra else None,
                ip_address=ip_address,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception:
        # Audit log must never break the main request
        logger.exception("Failed to write audit log entry: action=%r", action)
