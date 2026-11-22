"""Registro e consulta de audit logs (sem segredos)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def record_audit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    event_data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        account_id=account_id,
        event_data=event_data or {},
        ip=ip,
    )
    db.add(log)
    db.commit()
    return log


def list_audit_logs(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    action: str | None,
    account_id: uuid.UUID | None,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> tuple[list[AuditLog], bool]:
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if account_id is not None:
        stmt = stmt.where(AuditLog.account_id == account_id)
    if cursor is not None:
        stmt = stmt.where(tuple_(AuditLog.created_at, AuditLog.id) < cursor)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
    rows = list(db.scalars(stmt))
    return rows[:limit], len(rows) > limit
