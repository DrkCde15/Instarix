from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_job_service, require
from app.api.pagination import decode_cursor, encode_cursor
from app.api.request_info import client_ip
from app.db.session import get_db
from app.schemas.job import JobCreate, JobOut, JobPage
from app.services.audit import record_audit
from app.services.jobs import JobPageResult, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
account_router = APIRouter(prefix="/accounts", tags=["jobs"])


def _job_page(page: JobPageResult) -> JobPage:
    items = [JobOut.model_validate(job) for job in page.items]
    next_cursor = (
        encode_cursor(page.items[-1].created_at, page.items[-1].id)
        if page.has_more and page.items
        else None
    )
    return JobPage(items=items, next_cursor=next_cursor)


@account_router.post(
    "/{account_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    account_id: UUID,
    payload: JobCreate,
    response: Response,
    request: Request,
    principal: Principal = Depends(require("jobs:write")),
    service: JobService = Depends(get_job_service),
    db: Session = Depends(get_db),
) -> JobOut:
    result = service.create(
        principal.tenant_id, account_id, payload, principal.user_id
    )
    if result.created:
        record_audit(
            db,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="job.created",
            account_id=account_id,
            event_data={"job_id": str(result.job.id), "type": result.job.type},
            ip=client_ip(request),
        )
    response.status_code = (
        status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
    )
    response.headers["Location"] = f"/v1/jobs/{result.job.id}"
    return JobOut.model_validate(result.job)


@account_router.get("/{account_id}/jobs", response_model=JobPage)
def list_account_jobs(
    account_id: UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    principal: Principal = Depends(require("jobs:read")),
    service: JobService = Depends(get_job_service),
) -> JobPage:
    page = service.list(
        principal.tenant_id,
        account_id=account_id,
        status=status_filter,
        job_type=job_type,
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    return _job_page(page)


@router.get("", response_model=JobPage)
def list_jobs(
    account_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    principal: Principal = Depends(require("jobs:read")),
    service: JobService = Depends(get_job_service),
) -> JobPage:
    page = service.list(
        principal.tenant_id,
        account_id=account_id,
        status=status_filter,
        job_type=job_type,
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    return _job_page(page)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: UUID,
    principal: Principal = Depends(require("jobs:read")),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    return JobOut.model_validate(service.get(principal.tenant_id, job_id))


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: UUID,
    principal: Principal = Depends(require("jobs:write")),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    return JobOut.model_validate(service.cancel(principal.tenant_id, job_id))
