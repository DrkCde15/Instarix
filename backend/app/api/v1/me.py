from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.errors import unauthorized
from app.db.models import Tenant, User
from app.db.session import get_db
from app.schemas.auth import MeOut

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeOut)
def me(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> MeOut:
    if principal.user_id is None:
        raise unauthorized("user_required", "Esta rota exige um usuário autenticado.")
    user = db.get(User, principal.user_id)
    tenant = db.get(Tenant, principal.tenant_id)
    if user is None or tenant is None:
        raise unauthorized("invalid_token", "Usuário ou tenant não encontrado.")

    return MeOut(
        user_id=user.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        email=user.email,
        role=user.role,
    )
