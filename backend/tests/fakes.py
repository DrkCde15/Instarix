"""Fake do gateway do Instagram para testes sem rede."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.ig_gateway import (
    DownloadedMedia,
    HealthOutcome,
    LoginOutcome,
    PublishedMedia,
)


def success_outcome(device_settings: dict[str, Any] | None = None) -> LoginOutcome:
    session: dict[str, Any] = {
        "authorization_data": {
            "ds_user_id": "123",
            "sessionid": "sessao-secreta",
        },
        "cookies": {"sessionid": "sessao-secreta", "csrftoken": "csrf"},
        "uuids": {"uuid": "22222222-2222-2222-2222-222222222222"},
    }
    if device_settings is not None:
        session["device_settings"] = device_settings
    return LoginOutcome("ok", session=session)


@dataclass
class FakeIgGateway:
    login_outcome: LoginOutcome | None = None
    health_outcome: HealthOutcome = field(default_factory=lambda: HealthOutcome("ok"))
    login_calls: list[dict[str, Any]] = field(default_factory=list)
    health_calls: list[dict[str, Any]] = field(default_factory=list)
    logout_calls: list[dict[str, Any]] = field(default_factory=list)
    media_items: list[dict[str, Any]] = field(default_factory=list)
    direct_messages: list[dict[str, Any]] = field(default_factory=list)
    comment_items: list[dict[str, Any]] = field(default_factory=list)
    direct_calls: list[dict[str, Any]] = field(default_factory=list)
    comment_calls: list[dict[str, Any]] = field(default_factory=list)
    insights_data: dict[str, Any] = field(default_factory=dict)
    media_list_error: Exception | None = None
    download_error: Exception | None = None
    insights_error: Exception | None = None
    media_list_calls: list[dict[str, Any]] = field(default_factory=list)
    download_calls: list[dict[str, Any]] = field(default_factory=list)
    insights_calls: list[dict[str, Any]] = field(default_factory=list)
    publish_calls: list[dict[str, Any]] = field(default_factory=list)
    publish_error: Exception | None = None
    published_media_pk: str = "555000111"
    published_code: str = "POST123"

    def __post_init__(self) -> None:
        if self.login_outcome is None:
            self.login_outcome = success_outcome()

    def login(self, **kwargs: Any) -> LoginOutcome:
        self.login_calls.append(kwargs)
        assert self.login_outcome is not None
        return self.login_outcome

    def health(self, **kwargs: Any) -> HealthOutcome:
        self.health_calls.append(kwargs)
        return self.health_outcome

    def logout(self, **kwargs: Any) -> None:
        self.logout_calls.append(kwargs)

    def media_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.media_list_calls.append(kwargs)
        if self.media_list_error is not None:
            raise self.media_list_error
        return list(self.media_items)

    def direct_threads(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self.direct_messages)

    def direct_answer(self, *, thread_id: str, message: str, **kwargs: Any) -> None:
        self.direct_calls.append({"thread_id": thread_id, "message": message})

    def recent_comments(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self.comment_items)

    def reply_comment(
        self, *, media_pk: str, comment_id: str, message: str, **kwargs: Any
    ) -> None:
        self.comment_calls.append(
            {"media_pk": media_pk, "comment_id": comment_id, "message": message}
        )

    def media_download(
        self, *, media_pk: str, kinds: list[str], folder: Path, **kwargs: Any
    ) -> list[DownloadedMedia]:
        self.download_calls.append({"media_pk": media_pk, "kinds": kinds, **kwargs})
        if self.download_error is not None:
            raise self.download_error
        folder.mkdir(parents=True, exist_ok=True)
        suffix = {"photo": ".jpg", "video": ".mp4"}
        downloaded = []
        for kind in kinds:
            path = folder / f"{media_pk}_{kind}{suffix[kind]}"
            path.write_bytes(f"conteudo-{kind}".encode())
            downloaded.append(DownloadedMedia(kind, path))
        return downloaded

    def insights_account(self, **kwargs: Any) -> dict[str, Any]:
        self.insights_calls.append(kwargs)
        if self.insights_error is not None:
            raise self.insights_error
        return dict(self.insights_data)

    def _publish(self, action: str, **kwargs: Any) -> PublishedMedia:
        self.publish_calls.append({"action": action, **kwargs})
        if self.publish_error is not None:
            raise self.publish_error
        return PublishedMedia(self.published_media_pk, self.published_code)

    def publish_photo(self, **kwargs: Any) -> PublishedMedia:
        return self._publish("photo", **kwargs)

    def publish_video(self, **kwargs: Any) -> PublishedMedia:
        return self._publish("video", **kwargs)

    def publish_reel(self, **kwargs: Any) -> PublishedMedia:
        return self._publish("reel", **kwargs)

    def publish_album(self, **kwargs: Any) -> PublishedMedia:
        return self._publish("album", **kwargs)

    def publish_story(self, **kwargs: Any) -> PublishedMedia:
        return self._publish("story", **kwargs)
