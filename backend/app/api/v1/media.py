from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse

from app.api.deps import (
    Principal,
    get_job_service,
    get_read_service,
    require,
)
from app.schemas.job import JobCreate, JobOut
from app.schemas.media import InsightsSnapshotOut, MediaListOut
from app.services.jobs import JobService
from app.services.read import ReadService

router = APIRouter(tags=["media"])


@router.get("/accounts/{account_id}/media", response_model=MediaListOut)
def cached_media(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:read")),
    service: ReadService = Depends(get_read_service),
) -> MediaListOut:
    job = service.latest_media_job(principal.tenant_id, account_id)
    result = job.result or {}
    return MediaListOut(
        job_id=job.id,
        username=result.get("username") or "",
        items=result.get("items") or [],
        cached_at=job.finished_at,
    )


@router.get("/media/{asset_id}")
def download_media(
    asset_id: UUID,
    principal: Principal = Depends(require("accounts:read")),
    service: ReadService = Depends(get_read_service),
) -> FileResponse:
    asset, path = service.media_asset(principal.tenant_id, asset_id)
    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=f"{asset.media_pk}_{asset.kind}{path.suffix}",
    )


@router.get(
    "/accounts/{account_id}/insights", response_model=InsightsSnapshotOut
)
def latest_insights(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:read")),
    service: ReadService = Depends(get_read_service),
) -> InsightsSnapshotOut:
    return InsightsSnapshotOut.model_validate(
        service.latest_insights(principal.tenant_id, account_id)
    )


@router.post(
    "/accounts/{account_id}/insights/sync",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_insights(
    account_id: UUID,
    response: Response,
    principal: Principal = Depends(require("jobs:write")),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    result = service.create(
        principal.tenant_id,
        account_id,
        JobCreate(type="insights.account"),
        principal.user_id,
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
    )
    response.headers["Location"] = f"/v1/jobs/{result.job.id}"
    return JobOut.model_validate(result.job)
