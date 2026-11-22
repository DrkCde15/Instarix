from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require
from app.core.errors import forbidden, not_found
from app.core.security import generate_api_key
from app.core.time import utcnow
from app.db.models import ApiKey
from app.db.session import get_db
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    principal: Principal = Depends(require("keys:manage")),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    keys = db.scalars(
        select(ApiKey)
        .where(ApiKey.tenant_id == principal.tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyOut.model_validate(key) for key in keys]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(require("keys:manage")),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    # Uma key nunca pode receber mais poder que o principal que a criou.
    if not principal.has("*") and not set(payload.scopes).issubset(principal.scopes):
        raise forbidden(
            "scope_exceeds_principal",
            "A API key não pode ter escopos que o usuário não possui.",
        )

    raw_key, prefix, secret_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        name=payload.name,
        key_prefix=prefix,
        key_hash=secret_hash,
        scopes=payload.scopes,
    )
    db.add(api_key)
    db.commit()
    return ApiKeyCreated(
        **ApiKeyOut.model_validate(api_key).model_dump(), key=raw_key
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: UUID,
    principal: Principal = Depends(require("keys:manage")),
    db: Session = Depends(get_db),
) -> Response:
    api_key = db.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id, ApiKey.tenant_id == principal.tenant_id
        )
    )
    if api_key is None:
        raise not_found("api_key_not_found", "API key não encontrada.")
    if api_key.revoked_at is None:
        api_key.revoked_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
