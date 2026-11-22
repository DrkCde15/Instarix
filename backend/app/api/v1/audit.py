from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Principal, require
from app.api.pagination import decode_cursor, encode_cursor
from app.db.session import get_db
from app.schemas.audit import AuditLogOut, AuditLogPage
from app.services.audit import list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditLogPage)
def get_audit_logs(
    action: str | None = Query(default=None),
    account_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    principal: Principal = Depends(require("audit:read")),
    db: Session = Depends(get_db),
) -> AuditLogPage:
    rows, has_more = list_audit_logs(
        db,
        principal.tenant_id,
        action=action,
        account_id=account_id,
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    items = [
        AuditLogOut(
            id=row.id,
            user_id=row.user_id,
            action=row.action,
            account_id=row.account_id,
            metadata=row.event_data,
            ip=row.ip,
            created_at=row.created_at,
        )
        for row in rows
    ]
    next_cursor = (
        encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    )
    return AuditLogPage(items=items, next_cursor=next_cursor)
