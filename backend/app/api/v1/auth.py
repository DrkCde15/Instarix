from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.request_info import client_ip
from app.core.config import Settings, get_settings
from app.core.errors import AppError, unauthorized
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


def _cookie_attrs(settings: Settings) -> dict[str, object]:
    return {
        "key": settings.auth_refresh_cookie_name,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
        "path": settings.auth_cookie_path,
    }


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        value=token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        **_cookie_attrs(settings),
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(**_cookie_attrs(settings))


def _submitted_refresh_token(
    request: Request, payload: RefreshIn | None, settings: Settings
) -> str | None:
    if payload is not None and payload.refresh_token:
        return payload.refresh_token
    return request.cookies.get(settings.auth_refresh_cookie_name)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    guard.limit_register_ip(client_ip(request) or "unknown")
    _, tokens = auth_service.register(
        db,
        settings,
        tenant_name=payload.tenant_name,
        email=str(payload.email),
        password=payload.password,
    )
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_pair(tokens)


@router.post("/token", response_model=TokenPair)
def token(
    payload: TokenIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    email = str(payload.email)
    guard.limit_login_ip(client_ip(request) or "unknown")
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
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_pair(tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    request: Request,
    response: Response,
    payload: RefreshIn | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    guard: AuthGuard = Depends(get_auth_guard),
) -> TokenPair:
    guard.limit_refresh_ip(client_ip(request) or "unknown")
    raw_refresh = _submitted_refresh_token(request, payload, settings)
    if not raw_refresh:
        raise unauthorized("missing_refresh_token", "Informe o refresh token.")
    tokens = auth_service.rotate_refresh_token(db, settings, raw_refresh)
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_pair(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    payload: RefreshIn | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    raw_refresh = _submitted_refresh_token(request, payload, settings)
    if raw_refresh:
        auth_service.revoke_refresh_token(db, raw_refresh)
    _clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
