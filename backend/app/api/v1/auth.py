from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.ratelimit import AuthGuard, get_auth_guard
from app.db.session import get_db
from app.schemas.auth import RefreshIn, RegisterIn, TokenIn, TokenPair
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(tokens: auth_service.IssuedTokens) -> TokenPair:
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    guard.limit_register_ip(_client_ip(request))
    _, tokens = auth_service.register(
        db,
        settings,
        tenant_name=payload.tenant_name,
        email=str(payload.email),
        password=payload.password,
    )
    return _token_pair(tokens)


@router.post("/token", response_model=TokenPair)
def token(
    payload: TokenIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    email = str(payload.email)
    guard.limit_login_ip(_client_ip(request))
    guard.check_login_account(email)

    try:
        _, tokens = auth_service.authenticate(
            db, settings, email=email, password=payload.password
        )
    except AppError as exc:
        if exc.code == "invalid_credentials":
            guard.record_login_failure(email)
        raise

    guard.clear_login_failures(email)
    return _token_pair(tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    guard.limit_refresh_ip(_client_ip(request))
    return _token_pair(auth_service.rotate_refresh_token(db, settings, payload.refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshIn, db: Session = Depends(get_db)) -> Response:
    auth_service.revoke_refresh_token(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
