"""Dependências de autenticação, RBAC e serviços."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import Cipher, get_cipher
from app.core.errors import forbidden, unauthorized
from app.core.permissions import permissions_for_role
from app.core.security import (
    decode_access_token,
    parse_api_key,
    verify_api_key_secret,
)
from app.core.time import as_utc, utcnow
from app.db.models import ApiKey, User
from app.db.session import get_db
from app.services.accounts import AccountService
from app.services.device import DeviceProfileProvider, get_device_provider
from app.services.ig_gateway import IgGateway, get_ig_gateway
from app.services.jobs import JobService
from app.services.login import LoginService
from app.services.read import ReadService
from app.services.storage import MediaStorage, get_media_storage
from app.services.uploads import UploadService
from app.services.webhooks import WebhookService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str | None
    scopes: frozenset[str]
    auth_type: str

    def has(self, permission: str) -> bool:
        return "*" in self.scopes or permission in self.scopes


def _principal_from_jwt(
    token: str, db: Session, settings: Settings
) -> Principal:
    try:
        payload = decode_access_token(token, settings)
        user_id = uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise unauthorized("invalid_token", "Token de acesso inválido.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("invalid_token", "Token de acesso inválido.")
    if not user.is_active:
        raise forbidden("user_inactive", "Usuário desativado.")

    return Principal(
        tenant_id=user.tenant_id,
        user_id=user.id,
        role=user.role,
        scopes=permissions_for_role(user.role),
        auth_type="jwt",
    )


def _principal_from_api_key(raw_key: str, db: Session) -> Principal:
    parsed = parse_api_key(raw_key)
    if parsed is None:
        raise unauthorized("invalid_api_key", "API key inválida.")
    prefix, secret = parsed
    api_key = db.scalar(
        select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.revoked_at.is_(None))
    )
    if api_key is None or not verify_api_key_secret(secret, api_key.key_hash):
        raise unauthorized("invalid_api_key", "API key inválida.")

    now = utcnow()
    if (
        api_key.last_used_at is None
        or now - as_utc(api_key.last_used_at) > timedelta(seconds=60)
    ):
        api_key.last_used_at = now
        db.commit()

    return Principal(
        tenant_id=api_key.tenant_id,
        user_id=api_key.created_by,
        role=None,
        scopes=frozenset(api_key.scopes),
        auth_type="api_key",
    )


def get_principal(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    if x_api_key:
        return _principal_from_api_key(x_api_key, db)
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return _principal_from_jwt(credentials.credentials, db, settings)
    raise unauthorized("missing_credentials", "Informe um Bearer token ou X-API-Key.")


def require(permission: str) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise forbidden(
                "insufficient_permission",
                f"Permissão necessária: {permission}.",
            )
        return principal

    return dependency


def get_account_service(
    db: Session = Depends(get_db),
    cipher: Cipher = Depends(get_cipher),
    device_provider: DeviceProfileProvider = Depends(get_device_provider),
) -> AccountService:
    return AccountService(db, cipher, device_provider)


def get_login_service(
    db: Session = Depends(get_db),
    cipher: Cipher = Depends(get_cipher),
    gateway: IgGateway = Depends(get_ig_gateway),
) -> LoginService:
    return LoginService(db, cipher, gateway)


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db)


def get_read_service(
    db: Session = Depends(get_db),
    storage: MediaStorage = Depends(get_media_storage),
) -> ReadService:
    return ReadService(db, storage)


def get_upload_service(
    storage: MediaStorage = Depends(get_media_storage),
    settings: Settings = Depends(get_settings),
) -> UploadService:
    return UploadService(storage, settings)


def get_webhook_service(
    db: Session = Depends(get_db),
    cipher: Cipher = Depends(get_cipher),
    settings: Settings = Depends(get_settings),
) -> WebhookService:
    return WebhookService(db, cipher, settings)
