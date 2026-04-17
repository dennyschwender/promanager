"""models/audit_log.py — Audit log for tracking user actions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    # Who performed the action (nullable = system/anonymous)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # What happened — dot-namespaced e.g. "auth.login", "event.delete"
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # What was acted on
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Extra JSON context (e.g. {"old": "present", "new": "absent"})
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IP address of the actor
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
