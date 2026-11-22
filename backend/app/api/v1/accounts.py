from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    Principal,
    get_account_service,
    get_login_service,
    require,
)
from app.api.pagination import decode_cursor, encode_cursor
from app.schemas.account import (
    AccountCreate,
    AccountOut,
    AccountPage,
    AccountUpdate,
    LoginAttemptOut,
    TwoFactorIn,
)
from app.services.accounts import AccountService
from app.services.login import LoginService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountPage)
def list_accounts(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    principal: Principal = Depends(require("accounts:read")),
    service: AccountService = Depends(get_account_service),
) -> AccountPage:
    page = service.list(
        principal.tenant_id,
        status=status_filter,
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    items = [AccountOut.model_validate(account) for account in page.items]
    next_cursor = (
        encode_cursor(page.items[-1].created_at, page.items[-1].id)
        if page.has_more and page.items
        else None
    )
    return AccountPage(items=items, next_cursor=next_cursor)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    principal: Principal = Depends(require("accounts:write")),
    service: AccountService = Depends(get_account_service),
) -> AccountOut:
    account = service.create(principal.tenant_id, payload)
    return AccountOut.model_validate(account)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:read")),
    service: AccountService = Depends(get_account_service),
) -> AccountOut:
    return AccountOut.model_validate(service.get(principal.tenant_id, account_id))


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    principal: Principal = Depends(require("accounts:write")),
    service: AccountService = Depends(get_account_service),
) -> AccountOut:
    return AccountOut.model_validate(
        service.update(principal.tenant_id, account_id, payload)
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:write")),
    service: AccountService = Depends(get_account_service),
) -> Response:
    service.soft_delete(principal.tenant_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{account_id}/login", response_model=AccountOut)
def login_account(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:write")),
    service: LoginService = Depends(get_login_service),
) -> AccountOut:
    return AccountOut.model_validate(service.login(principal.tenant_id, account_id))


@router.post("/{account_id}/2fa", response_model=AccountOut)
def submit_two_factor(
    account_id: UUID,
    payload: TwoFactorIn,
    principal: Principal = Depends(require("accounts:2fa")),
    service: LoginService = Depends(get_login_service),
) -> AccountOut:
    return AccountOut.model_validate(
        service.submit_2fa(principal.tenant_id, account_id, payload.code)
    )


@router.post("/{account_id}/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_account(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:write")),
    service: LoginService = Depends(get_login_service),
) -> Response:
    service.logout(principal.tenant_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{account_id}/health", response_model=AccountOut)
def account_health(
    account_id: UUID,
    principal: Principal = Depends(require("accounts:read")),
    service: LoginService = Depends(get_login_service),
) -> AccountOut:
    return AccountOut.model_validate(service.health(principal.tenant_id, account_id))


@router.get("/{account_id}/login-attempts", response_model=list[LoginAttemptOut])
def account_login_attempts(
    account_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require("accounts:read")),
    service: LoginService = Depends(get_login_service),
) -> list[LoginAttemptOut]:
    attempts = service.list_attempts(principal.tenant_id, account_id, limit)
    return [LoginAttemptOut.model_validate(attempt) for attempt in attempts]
