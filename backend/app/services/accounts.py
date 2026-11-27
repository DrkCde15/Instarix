"""CRUD de contas do Instagram com segredos cifrados."""

import ipaddress
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import Cipher
from app.core.errors import AppError, conflict, not_found
from app.core.time import utcnow
from app.db.models.account import IgAccount, IgAccountStatus
from app.schemas.account import AccountCreate, AccountUpdate
from app.services.device import DeviceProfileProvider


@dataclass(frozen=True)
class AccountPageResult:
    items: list[IgAccount]
    has_more: bool


def _proxy_host_allowed(host: str, port: int, *, allow_private: bool) -> bool:
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return allow_private
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if allow_private:
            return True
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            return False
        return all(
            ipaddress.ip_address(info[4][0]).is_global for info in infos
        )
    return allow_private or address.is_global


def _validate_proxy(proxy: str, *, allow_private: bool) -> str:
    proxy = proxy.strip()
    parts = urlsplit(proxy)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AppError(422, "invalid_proxy", "proxy deve ser uma URL http(s) com host.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise AppError(422, "invalid_proxy", "porta inválida no proxy.") from exc
    if not _proxy_host_allowed(parts.hostname.lower(), port, allow_private=allow_private):
        raise AppError(422, "invalid_proxy", "proxy aponta para um host não permitido.")
    return proxy


class AccountService:
    def __init__(
        self,
        db: Session,
        cipher: Cipher,
        device_provider: DeviceProfileProvider,
        settings: Settings | None = None,
    ):
        self.db = db
        self.cipher = cipher
        self.device_provider = device_provider
        self.settings = settings or get_settings()

    def create(self, tenant_id: uuid.UUID, data: AccountCreate) -> IgAccount:
        device_settings = self.device_provider.generate()
        account = IgAccount(
            tenant_id=tenant_id,
            label=data.label,
            username=data.username,
            password_enc=self.cipher.encrypt(data.password),
            proxy_enc=(
                self.cipher.encrypt(
                    _validate_proxy(
                        data.proxy, allow_private=self.settings.allow_private_proxies
                    )
                )
                if data.proxy
                else None
            ),
            device_settings_enc=self.cipher.encrypt_json(device_settings),
            status=IgAccountStatus.PENDING_LOGIN,
        )
        self.db.add(account)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict(
                "account_exists", "Já existe uma conta com esse username neste tenant."
            ) from exc
        return account

    def get(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
        account = self.db.scalar(
            select(IgAccount).where(
                IgAccount.id == account_id,
                IgAccount.tenant_id == tenant_id,
                IgAccount.deleted_at.is_(None),
            )
        )
        if account is None:
            raise not_found("account_not_found", "Conta não encontrada.")
        return account

    def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: str | None,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None,
    ) -> AccountPageResult:
        if status is not None and status not in IgAccountStatus.ALL:
            raise AppError(422, "invalid_status", "status inválido.")

        stmt = select(IgAccount).where(
            IgAccount.tenant_id == tenant_id, IgAccount.deleted_at.is_(None)
        )
        if status is not None:
            stmt = stmt.where(IgAccount.status == status)
        if cursor is not None:
            stmt = stmt.where(
                tuple_(IgAccount.created_at, IgAccount.id) < (cursor[0], cursor[1])
            )
        stmt = stmt.order_by(IgAccount.created_at.desc(), IgAccount.id.desc()).limit(limit + 1)

        rows = list(self.db.scalars(stmt))
        has_more = len(rows) > limit
        return AccountPageResult(items=rows[:limit], has_more=has_more)

    def update(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate
    ) -> IgAccount:
        account = self.get(tenant_id, account_id)
        fields = data.model_fields_set

        if data.label is not None:
            account.label = data.label

        if "password" in fields and data.password is not None:
            account.password_enc = self.cipher.encrypt(data.password)
            account.status = IgAccountStatus.NEEDS_REAUTH
            account.session_enc = None
            account.last_error_code = None
            account.last_error_message = None

        if "proxy" in fields:
            if data.proxy:
                account.proxy_enc = self.cipher.encrypt(
                    _validate_proxy(
                        data.proxy, allow_private=self.settings.allow_private_proxies
                    )
                )
            else:
                account.proxy_enc = None

        self.db.commit()
        return account

    def soft_delete(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> None:
        account = self.get(tenant_id, account_id)
        account.deleted_at = utcnow()
        account.session_enc = None
        account.status = IgAccountStatus.DISABLED
        self.db.commit()
