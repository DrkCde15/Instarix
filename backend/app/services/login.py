"""Login real no Instagram, 2FA, sessão e máquina de estados por conta."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import Cipher, SecretDecryptError
from app.core.errors import AppError, conflict, not_found
from app.core.time import as_utc, utcnow
from app.db.models.account import IgAccount, IgAccountStatus
from app.db.models.login_attempt import LoginAttempt, LoginAttemptStatus
from app.services.ig_gateway import IgGateway, LoginOutcome

logger = logging.getLogger(__name__)

TWO_FA_TTL = timedelta(minutes=10)
MAX_2FA_ATTEMPTS = 3


@dataclass(frozen=True)
class AccountCredentials:
    username: str
    password: str
    device_settings: dict[str, Any]
    proxy: str | None
    session: dict[str, Any] | None


class LoginService:
    def __init__(self, db: Session, cipher: Cipher, gateway: IgGateway) -> None:
        self.db = db
        self.cipher = cipher
        self.gateway = gateway

    # -- ações ----------------------------------------------------------

    def login(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
        account = self._get_locked(tenant_id, account_id)
        if account.status == IgAccountStatus.DISABLED:
            raise conflict("account_disabled", "Conta desativada.")
        if account.status == IgAccountStatus.CHALLENGE_REQUIRED:
            # Só chega aqui depois de o usuário resolver o desafio no app.
            logger.info("account_challenge_retry account_id=%s", account.id)

        credentials = self._credentials(account)
        self._expire_pending_attempts(account, utcnow())

        outcome = self.gateway.login(
            username=credentials.username,
            password=credentials.password,
            device_settings=credentials.device_settings,
            proxy=credentials.proxy,
            session=credentials.session,
        )
        return self._apply_outcome(account, outcome, verification_code=None)

    def submit_2fa(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID, code: str
    ) -> IgAccount:
        account = self._get_locked(tenant_id, account_id)
        if account.status != IgAccountStatus.TWO_FA_REQUIRED:
            raise conflict(
                "two_factor_not_pending",
                "Não há login aguardando código de verificação.",
            )

        attempt = self._pending_attempt(account)
        now = utcnow()
        if attempt is None:
            raise conflict(
                "two_factor_not_pending",
                "Não há login aguardando código de verificação.",
            )
        if attempt.expires_at is None or as_utc(attempt.expires_at) <= now:
            self._finish_attempt(attempt, LoginAttemptStatus.EXPIRED, now)
            self._transition(account, IgAccountStatus.PENDING_LOGIN, "two_factor_expired")
            account.last_error_code = "two_factor_expired"
            account.last_error_message = "Código expirado; inicie o login novamente."
            self.db.commit()
            raise conflict(
                "two_factor_expired", "Código expirado; inicie o login novamente."
            )

        credentials = self._credentials(account)
        outcome = self.gateway.login(
            username=credentials.username,
            password=credentials.password,
            device_settings=credentials.device_settings,
            proxy=credentials.proxy,
            session=None,
            verification_code=code,
        )
        return self._apply_outcome(account, outcome, verification_code=code, attempt=attempt)

    def logout(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> None:
        account = self._get_locked(tenant_id, account_id)
        session = self._stored_session(account)
        if session is not None:
            self.gateway.logout(
                username=account.username,
                proxy=self._stored_proxy(account),
                session=session,
            )

        account.session_enc = None
        account.status = IgAccountStatus.PENDING_LOGIN
        account.last_error_code = None
        account.last_error_message = None
        self.db.commit()

    def health(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
        account = self._get_locked(tenant_id, account_id)
        session = self._stored_session(account)
        if session is None:
            raise conflict(
                "account_no_session",
                "A conta não tem sessão salva; faça login primeiro.",
            )

        outcome = self.gateway.health(
            username=account.username,
            proxy=self._stored_proxy(account),
            session=session,
        )
        if outcome.status == "ok":
            account.last_health_at = utcnow()
            self.db.commit()
            return account

        if outcome.status == "invalid":
            account.session_enc = None
            account.last_health_at = utcnow()
            self._transition(
                account, IgAccountStatus.NEEDS_REAUTH, "session_invalid"
            )
            account.last_error_code = "account_needs_reauth"
            account.last_error_message = "A sessão salva foi recusada pelo Instagram."
            self.db.commit()
            return account

        raise AppError(
            502,
            "instagram_unavailable",
            "Não foi possível validar a sessão no Instagram agora.",
        )

    def list_attempts(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID, limit: int = 50
    ) -> list[LoginAttempt]:
        self._get(tenant_id, account_id)
        return list(
            self.db.scalars(
                select(LoginAttempt)
                .where(
                    LoginAttempt.tenant_id == tenant_id,
                    LoginAttempt.account_id == account_id,
                )
                .order_by(LoginAttempt.created_at.desc())
                .limit(limit)
            )
        )

    # -- resultado do gateway ------------------------------------------

    def _apply_outcome(
        self,
        account: IgAccount,
        outcome: LoginOutcome,
        *,
        verification_code: str | None,
        attempt: LoginAttempt | None = None,
    ) -> IgAccount:
        now = utcnow()

        if outcome.status == "ok":
            if not outcome.session:
                raise AppError(
                    502,
                    "instagram_error",
                    "O Instagram não retornou uma sessão utilizável.",
                )
            account.session_enc = self.cipher.encrypt_json(outcome.session)
            account.status = IgAccountStatus.ACTIVE
            account.last_login_at = now
            account.last_health_at = now
            account.last_error_code = None
            account.last_error_message = None
            if attempt is not None:
                self._finish_attempt(attempt, LoginAttemptStatus.SUCCEEDED, now)
            else:
                self._new_attempt(account, LoginAttemptStatus.SUCCEEDED, now).finished_at = now
            self.db.commit()
            logger.info("account_login_succeeded account_id=%s", account.id)
            return account

        if outcome.status == "2fa_required":
            if verification_code is None:
                self._transition(account, IgAccountStatus.TWO_FA_REQUIRED, "two_factor_required")
                account.session_enc = None
                account.last_error_code = "2fa_required"
                account.last_error_message = "Aguardando código de verificação em duas etapas."
                pending = self._new_attempt(
                    account, LoginAttemptStatus.PENDING_2FA, now
                )
                pending.expires_at = now + TWO_FA_TTL
                pending.method = outcome.two_fa_method
                self.db.commit()
                return account

            # Código errado (ou recusado) dentro de um attempt pendente.
            assert attempt is not None
            attempt.attempts += 1
            attempt.error_code = "invalid_verification_code"
            if attempt.attempts >= MAX_2FA_ATTEMPTS:
                self._finish_attempt(attempt, LoginAttemptStatus.FAILED, now)
                self._transition(
                    account, IgAccountStatus.NEEDS_REAUTH, "too_many_2fa_attempts"
                )
                account.session_enc = None
                account.last_error_code = "invalid_verification_code"
                account.last_error_message = (
                    "Muitos códigos inválidos; inicie o login novamente."
                )
                self.db.commit()
                raise AppError(
                    400,
                    "invalid_verification_code",
                    "Código inválido. Nenhuma tentativa restante; inicie o login novamente.",
                )

            attempt.expires_at = now + TWO_FA_TTL
            self.db.commit()
            remaining = MAX_2FA_ATTEMPTS - attempt.attempts
            raise AppError(
                400,
                "invalid_verification_code",
                f"Código inválido. Tentativas restantes: {remaining}.",
            )

        if outcome.status == "challenge_required":
            self._transition(
                account, IgAccountStatus.CHALLENGE_REQUIRED, "instagram_challenge"
            )
            account.session_enc = None
            account.last_error_code = "account_challenge_required"
            account.last_error_message = outcome.error_message
            self._record_failure(account, attempt, "account_challenge_required", now)
            self.db.commit()
            raise conflict(
                "account_challenge_required",
                "O Instagram exige verificação no app oficial. Resolva o desafio e tente o login novamente.",
            )

        if outcome.status == "bad_password":
            self._transition(
                account, IgAccountStatus.NEEDS_REAUTH, outcome.error_code or "bad_password"
            )
            account.session_enc = None
            account.last_error_code = "account_needs_reauth"
            account.last_error_message = outcome.error_message
            self._record_failure(account, attempt, "account_needs_reauth", now)
            self.db.commit()
            raise conflict(
                "account_needs_reauth",
                "O Instagram recusou as credenciais. Atualize a senha da conta.",
            )

        # Falha transitória: não muda o status nem descarta a sessão, e não
        # consome a tentativa de 2FA pendente (o usuário pode tentar de novo).
        account.last_error_code = outcome.error_code or "instagram_unavailable"
        account.last_error_message = outcome.error_message
        if attempt is None:
            self._record_failure(
                account,
                None,
                account.last_error_code,
                now,
                status=LoginAttemptStatus.FAILED,
            )
        self.db.commit()
        raise AppError(
            502,
            outcome.error_code or "instagram_unavailable",
            outcome.error_message or "Falha temporária ao falar com o Instagram.",
        )

    # -- persistência / helpers ---------------------------------------

    def _get(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
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

    def _get_locked(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
        # No Postgres serializa operações da mesma conta; SQLite ignora.
        account = self.db.scalar(
            select(IgAccount)
            .where(
                IgAccount.id == account_id,
                IgAccount.tenant_id == tenant_id,
                IgAccount.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if account is None:
            raise not_found("account_not_found", "Conta não encontrada.")
        return account

    def _credentials(self, account: IgAccount) -> AccountCredentials:
        try:
            password = self.cipher.decrypt(account.password_enc)
            device_settings = self.cipher.decrypt_json(account.device_settings_enc)
        except SecretDecryptError as exc:
            raise conflict(
                "account_secrets_unreadable",
                "Não foi possível ler as credenciais da conta; atualize a senha.",
            ) from exc

        return AccountCredentials(
            username=account.username,
            password=password,
            device_settings=device_settings,
            proxy=self._stored_proxy(account),
            session=self._stored_session(account),
        )

    def _stored_session(self, account: IgAccount) -> dict[str, Any] | None:
        if account.session_enc is None:
            return None
        try:
            return self.cipher.decrypt_json(account.session_enc)
        except SecretDecryptError as exc:
            raise conflict(
                "account_session_unreadable",
                "Não foi possível ler a sessão salva; faça login novamente.",
            ) from exc

    def _stored_proxy(self, account: IgAccount) -> str | None:
        if account.proxy_enc is None:
            return None
        try:
            return self.cipher.decrypt(account.proxy_enc)
        except SecretDecryptError as exc:
            raise conflict(
                "account_secrets_unreadable",
                "Não foi possível ler o proxy da conta; atualize o proxy.",
            ) from exc

    def _pending_attempt(self, account: IgAccount) -> LoginAttempt | None:
        return self.db.scalar(
            select(LoginAttempt)
            .where(
                LoginAttempt.account_id == account.id,
                LoginAttempt.status == LoginAttemptStatus.PENDING_2FA,
            )
            .order_by(LoginAttempt.created_at.desc())
            .limit(1)
        )

    def _expire_pending_attempts(self, account: IgAccount, now: datetime) -> None:
        pending = self.db.scalars(
            select(LoginAttempt).where(
                LoginAttempt.account_id == account.id,
                LoginAttempt.status == LoginAttemptStatus.PENDING_2FA,
            )
        )
        for attempt in pending:
            self._finish_attempt(attempt, LoginAttemptStatus.EXPIRED, now)

    def _new_attempt(
        self, account: IgAccount, status: str, now: datetime
    ) -> LoginAttempt:
        attempt = LoginAttempt(
            tenant_id=account.tenant_id,
            account_id=account.id,
            status=status,
        )
        self.db.add(attempt)
        return attempt

    def _record_failure(
        self,
        account: IgAccount,
        attempt: LoginAttempt | None,
        error_code: str,
        now: datetime,
        *,
        status: str = LoginAttemptStatus.FAILED,
    ) -> None:
        target = attempt or self._new_attempt(account, status, now)
        self._finish_attempt(target, status, now, error_code)

    def _finish_attempt(
        self,
        attempt: LoginAttempt,
        status: str,
        now: datetime,
        error_code: str | None = None,
    ) -> None:
        attempt.status = status
        attempt.finished_at = now
        if error_code is not None:
            attempt.error_code = error_code

    def _transition(self, account: IgAccount, status: str, reason: str) -> None:
        previous = account.status
        if previous != status:
            logger.info(
                "account_status_changed account_id=%s from=%s to=%s reason=%s",
                account.id,
                previous,
                status,
                reason,
            )
        account.status = status
