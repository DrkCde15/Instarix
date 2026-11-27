from urllib.parse import urlsplit

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


def _no_store(response: Response) -> None:
    # Respostas com tokens nunca devem ficar em cache de navegador/proxy.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _is_loopback_host(value: str) -> bool:
    if value.startswith("["):  # IPv6 com porta: [::1]:5173
        host = value.split("]", 1)[0][1:]
    elif value.count(":") == 1:  # hostname/IPv4 com porta
        host = value.rsplit(":", 1)[0]
    else:
        host = value
    return host in {"localhost", "127.0.0.1", "::1"}


def _reject_cross_site_request(request: Request, settings: Settings) -> None:
    """Barrar CSRF nas rotas autenticadas por cookie.

    A defesa principal é SameSite (lax por padrão), mas quando o cookie é
    enviado a requisição precisa vir da mesma origem ou de uma origem
    explicitamente listada em CORS_ORIGINS.
    """
    origin = request.headers.get("origin")
    if not origin:
        return  # clientes não-browser e SameSite já cobrem esse caso
    try:
        origin_host = urlsplit(origin).netloc.lower()
    except ValueError:
        origin_host = ""
    if not origin_host:
        raise AppError(403, "csrf_origin_rejected", "Origem não permitida.")

    request_host = request.headers.get("host", "").lower()
    allowed = {entry.rstrip("/").lower() for entry in settings.cors_origins}
    if origin_host == request_host or origin.rstrip("/").lower() in allowed:
        return
    # O proxy de dev do Vite reescreve o Host; loopback->loopback é local.
    if _is_loopback_host(origin_host) and _is_loopback_host(request_host):
        return
    raise AppError(
        403,
        "csrf_origin_rejected",
        "Origem não permitida para operação com cookie de sessão.",
    )


def _submitted_refresh_token(
    request: Request, payload: RefreshIn | None, settings: Settings
) -> tuple[str | None, bool]:
    """Retorna (token, veio_do_cookie)."""
    if payload is not None and payload.refresh_token:
        return payload.refresh_token, False
    cookie = request.cookies.get(settings.auth_refresh_cookie_name)
    return cookie, cookie is not None


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
    _no_store(response)
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
    _no_store(response)
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
    raw_refresh, from_cookie = _submitted_refresh_token(request, payload, settings)
    if from_cookie:
        _reject_cross_site_request(request, settings)
    if not raw_refresh:
        raise unauthorized("missing_refresh_token", "Informe o refresh token.")
    tokens = auth_service.rotate_refresh_token(db, settings, raw_refresh)
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    _no_store(response)
    return _token_pair(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    payload: RefreshIn | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    raw_refresh, from_cookie = _submitted_refresh_token(request, payload, settings)
    if from_cookie:
        _reject_cross_site_request(request, settings)
    if raw_refresh:
        auth_service.revoke_refresh_token(db, raw_refresh)
    _clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
