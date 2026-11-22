from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, require
from app.db.session import get_db
from app.services.metrics import collect_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def metrics(
    principal: Principal = Depends(require("keys:manage")),
    db: Session = Depends(get_db),
) -> Response:
    return Response(
        content=collect_metrics(db, principal.tenant_id),
        media_type="text/plain; version=0.0.4",
    )
