"""Wrapper testável em volta do instagrapi.

Toda interação de rede com o Instagram passa por aqui. O serviço de login só
conhece ``IgGateway``, então os testes trocam a implementação real por um fake
via ``dependency_overrides`` sem tocar em rede.

As sessões retornadas são o ``dict`` de ``Client.get_settings()`` completo
(cookies, authorization_data, uuids, device). Elas nunca são logadas.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

LoginStatus = Literal[
    "ok", "2fa_required", "challenge_required", "bad_password", "unavailable"
]
HealthStatus = Literal["ok", "invalid", "unavailable"]


@dataclass(frozen=True)
class LoginOutcome:
    status: LoginStatus
    session: dict[str, Any] | None = None
    two_fa_method: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class HealthOutcome:
    status: HealthStatus


@dataclass(frozen=True)
class DownloadedMedia:
    kind: str
    path: Path


class IgGatewayError(Exception):
    """Erro de leitura já sanitizado para virar falha de job."""

    code = "instagram_error"
    retryable = False
    account_status: str | None = None

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IgAuthError(IgGatewayError):
    code = "account_needs_reauth"
    account_status = "needs_reauth"

    def __init__(self, message: str = "A sessão salva foi recusada pelo Instagram.") -> None:
        super().__init__(message)


class IgChallengeError(IgGatewayError):
    code = "account_challenge_required"
    account_status = "challenge_required"

    def __init__(self, message: str = "O Instagram exige verificação no app oficial.") -> None:
        super().__init__(message)


class IgUnavailableError(IgGatewayError):
    code = "instagram_unavailable"
    retryable = True

    def __init__(
        self, message: str = "Falha temporária ao falar com o Instagram."
    ) -> None:
        super().__init__(message)


class IgGateway(Protocol):
    def login(
        self,
        *,
        username: str,
        password: str,
        device_settings: dict[str, Any],
        proxy: str | None,
        session: dict[str, Any] | None = None,
        verification_code: str | None = None,
    ) -> LoginOutcome: ...

    def health(
        self,
        *,
        username: str,
        proxy: str | None,
        session: dict[str, Any],
    ) -> HealthOutcome: ...

    def logout(
        self,
        *,
        username: str,
        proxy: str | None,
        session: dict[str, Any],
    ) -> None: ...

    def media_list(
        self,
        *,
        username: str,
        amount: int,
        proxy: str | None,
        session: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def media_download(
        self,
        *,
        media_pk: str,
        kinds: list[str],
        proxy: str | None,
        session: dict[str, Any],
        folder: Path,
    ) -> list[DownloadedMedia]: ...

    def insights_account(
        self,
        *,
        proxy: str | None,
        session: dict[str, Any],
    ) -> dict[str, Any]: ...


class InstagrapiGateway:
    def _client(
        self,
        device_settings: dict[str, Any],
        proxy: str | None,
        session: dict[str, Any] | None,
    ):
        from instagrapi import Client

        settings: dict[str, Any] = dict(device_settings)
        if session:
            settings.update(session)

        client = Client()
        client.set_settings(settings)
        if proxy:
            client.set_proxy(proxy)
        client.delay_range = [1, 3]
        return client

    def login(
        self,
        *,
        username: str,
        password: str,
        device_settings: dict[str, Any],
        proxy: str | None,
        session: dict[str, Any] | None = None,
        verification_code: str | None = None,
    ) -> LoginOutcome:
        from instagrapi import Client
        from instagrapi.exceptions import (
            BadCredentials,
            BadPassword,
            ChallengeError,
            ClientConnectionError,
            ClientError,
            ClientRequestTimeout,
            ClientThrottledError,
            LoginRequired,
            PleaseWaitFewMinutes,
            ProxyAddressIsBlocked,
            RateLimitError,
            SentryBlock,
            TwoFactorRequired,
        )

        client: Client = self._client(device_settings, proxy, session)
        try:
            client.login(
                username=username,
                password=password,
                verification_code=verification_code or "",
            )
        except TwoFactorRequired:
            return LoginOutcome(
                "2fa_required",
                two_fa_method="unknown",
                error_code="2fa_required",
                error_message="Código de verificação em duas etapas necessário.",
            )
        except ChallengeError:
            return LoginOutcome(
                "challenge_required",
                error_code="account_challenge_required",
                error_message="O Instagram exige verificação no app oficial.",
            )
        except (BadPassword, BadCredentials):
            return LoginOutcome(
                "bad_password",
                error_code="account_needs_reauth",
                error_message="Senha recusada pelo Instagram.",
            )
        except LoginRequired:
            return LoginOutcome(
                "bad_password",
                error_code="account_needs_reauth",
                error_message="A sessão salva foi recusada pelo Instagram.",
            )
        except (
            PleaseWaitFewMinutes,
            RateLimitError,
            ClientThrottledError,
            ClientConnectionError,
            ClientRequestTimeout,
            SentryBlock,
            ProxyAddressIsBlocked,
        ) as exc:
            logger.warning("ig_login_unavailable error=%s", type(exc).__name__)
            return LoginOutcome(
                "unavailable",
                error_code="instagram_unavailable",
                error_message="Falha temporária ao falar com o Instagram.",
            )
        except ClientError as exc:
            # Não propagar mensagem/resposta crua: pode conter PII.
            logger.warning("ig_login_error error=%s", type(exc).__name__)
            return LoginOutcome(
                "unavailable",
                error_code="instagram_error",
                error_message="Erro inesperado no login do Instagram.",
            )

        try:
            session = client.get_settings()
        except Exception as exc:  # noqa: BLE001 - falha ao serializar sessão
            logger.exception("ig_session_serialize_failed error=%s", type(exc).__name__)
            return LoginOutcome(
                "unavailable",
                error_code="instagram_error",
                error_message="Login concluído, mas a sessão não pôde ser salva.",
            )

        return LoginOutcome("ok", session=session)

    def health(
        self,
        *,
        username: str,
        proxy: str | None,
        session: dict[str, Any],
    ) -> HealthOutcome:
        from instagrapi.exceptions import ClientError, LoginRequired

        client = self._client({}, proxy, session)
        try:
            client.account_info()
            return HealthOutcome("ok")
        except LoginRequired:
            return HealthOutcome("invalid")
        except ClientError as exc:
            logger.warning("ig_health_unavailable error=%s", type(exc).__name__)
            return HealthOutcome("unavailable")

    def logout(
        self,
        *,
        username: str,
        proxy: str | None,
        session: dict[str, Any],
    ) -> None:
        client = self._client({}, proxy, session)
        try:
            client.logout()
        except Exception as exc:  # noqa: BLE001 - logout é best-effort
            logger.warning("ig_logout_failed error=%s", type(exc).__name__)

    def _raise_read_error(self, exc: Exception) -> None:
        from instagrapi.exceptions import (
            ChallengeError,
            ClientConnectionError,
            ClientError,
            ClientRequestTimeout,
            ClientThrottledError,
            LoginRequired,
            PleaseWaitFewMinutes,
            ProxyAddressIsBlocked,
            RateLimitError,
            SentryBlock,
        )

        if isinstance(exc, LoginRequired):
            raise IgAuthError() from exc
        if isinstance(exc, ChallengeError):
            raise IgChallengeError() from exc
        if isinstance(
            exc,
            (
                PleaseWaitFewMinutes,
                RateLimitError,
                ClientThrottledError,
                ClientConnectionError,
                ClientRequestTimeout,
                SentryBlock,
                ProxyAddressIsBlocked,
            ),
        ):
            logger.warning("ig_read_unavailable error=%s", type(exc).__name__)
            raise IgUnavailableError() from exc
        if isinstance(exc, ClientError):
            logger.warning("ig_read_error error=%s", type(exc).__name__)
            raise IgGatewayError("Erro inesperado ao ler dados do Instagram.") from exc
        raise

    @staticmethod
    def _media_summary(media: Any) -> dict[str, Any]:
        taken_at = getattr(media, "taken_at", None)
        user = getattr(media, "user", None)
        return {
            "pk": str(getattr(media, "pk", "")),
            "id": str(getattr(media, "id", "")),
            "code": getattr(media, "code", None),
            "media_type": getattr(media, "media_type", None),
            "product_type": getattr(media, "product_type", None),
            "taken_at": taken_at.isoformat() if taken_at is not None else None,
            "caption": getattr(media, "caption_text", None),
            "thumbnail_url": getattr(media, "thumbnail_url", None),
            "video_url": getattr(media, "video_url", None),
            "like_count": getattr(media, "like_count", None),
            "comment_count": getattr(media, "comment_count", None),
            "username": getattr(user, "username", None),
        }

    def media_list(
        self,
        *,
        username: str,
        amount: int,
        proxy: str | None,
        session: dict[str, Any],
    ) -> list[dict[str, Any]]:
        client = self._client({}, proxy, session)
        try:
            user_id = client.user_id_from_username(username)
            medias = client.user_medias(user_id, amount=amount)
        except Exception as exc:  # noqa: BLE001 - mapeado abaixo
            self._raise_read_error(exc)
            raise
        return [self._media_summary(media) for media in medias]

    def media_download(
        self,
        *,
        media_pk: str,
        kinds: list[str],
        proxy: str | None,
        session: dict[str, Any],
        folder: Path,
    ) -> list[DownloadedMedia]:
        client = self._client({}, proxy, session)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            pk = int(media_pk)
            info = client.media_info(pk)
            media_type = int(getattr(info, "media_type", 0))
            downloaded: list[DownloadedMedia] = []

            if media_type == 8:
                for path in client.album_download(pk, folder=folder):
                    kind = "video" if path.suffix.lower() in {".mp4", ".mov"} else "photo"
                    if kind in kinds:
                        downloaded.append(DownloadedMedia(kind, path))
            elif media_type == 2 and "video" in kinds:
                downloaded.append(
                    DownloadedMedia("video", client.video_download(pk, folder=folder))
                )
            elif media_type == 1 and "photo" in kinds:
                downloaded.append(
                    DownloadedMedia("photo", client.photo_download(pk, folder=folder))
                )
            return downloaded
        except Exception as exc:  # noqa: BLE001 - mapeado abaixo
            self._raise_read_error(exc)
            raise

    def insights_account(
        self,
        *,
        proxy: str | None,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._client({}, proxy, session)
        try:
            data = client.insights_account()
        except Exception as exc:  # noqa: BLE001 - mapeado abaixo
            self._raise_read_error(exc)
            raise
        return dict(data)


def get_ig_gateway() -> IgGateway:
    return InstagrapiGateway()
