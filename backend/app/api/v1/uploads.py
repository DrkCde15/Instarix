from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import Principal, get_upload_service, require
from app.schemas.upload import UploadOut
from app.services.uploads import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    principal: Principal = Depends(require("jobs:write")),
    service: UploadService = Depends(get_upload_service),
) -> UploadOut:
    limit = service.settings.upload_max_bytes
    data = await file.read(limit + 1)
    key, content_type, size = service.save(
        principal.tenant_id,
        filename=file.filename or "",
        content_type=file.content_type or "",
        data=data,
    )
    return UploadOut(
        storage_key=key,
        filename=file.filename or "",
        content_type=content_type,
        size_bytes=size,
    )
