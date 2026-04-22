"""routes/admin.py — Admin-only pages (audit log, etc.)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.audit_log import AuditLog
from routes._auth_helpers import require_admin

router = APIRouter()

PAGE_SIZE = 50


@router.get("/audit")
async def audit_log(
    request: Request,
    page: int = 1,
    action: str = "",
    actor: str = "",
    target: str = "",
    ip: str = "",
    date_from: str = "",
    date_to: str = "",
    user: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor}%"))
    if target:
        query = query.filter(
            (AuditLog.target_label.ilike(f"%{target}%")) |
            (AuditLog.target_type.ilike(f"%{target}%"))
        )
    if ip:
        query = query.filter(AuditLog.ip_address.ilike(f"%{ip}%"))
    if date_from:
        try:
            from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(AuditLog.created_at >= from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            to_dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AuditLog.created_at < to_dt)
        except ValueError:
            pass

    total = query.count()
    offset = (page - 1) * PAGE_SIZE
    entries = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(PAGE_SIZE).all()

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return render(
        request,
        "admin/audit_log.html",
        {
            "user": user,
            "entries": entries,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "filter_action": action,
            "filter_actor": actor,
            "filter_target": target,
            "filter_ip": ip,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
        },
    )
