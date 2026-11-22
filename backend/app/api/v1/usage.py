from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_quota_service, require
from app.schemas.usage import UsageOut
from app.services.quotas import QuotaService

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("", response_model=UsageOut)
def get_usage(
    principal: Principal = Depends(require("accounts:read")),
    service: QuotaService = Depends(get_quota_service),
) -> UsageOut:
    usage = service.usage(principal.tenant_id)
    return UsageOut(
        plan=usage.plan,
        accounts_used=usage.accounts_used,
        accounts_limit=usage.accounts_limit,
        jobs_today_used=usage.jobs_today_used,
        jobs_today_limit=usage.jobs_today_limit,
    )
