"""Schemas de payload por tipo de job.

O payload é validado no enfileiramento e de novo no worker, para que um job
gravado por uma versão antiga nunca chegue cru ao handler.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
MEDIA_PK_RE = re.compile(r"^[0-9]{1,64}$")
CAPTION_MAX = 2200


def _storage_key(value: str) -> str:
    value = value.strip()
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or ".." in value.split("/")
    ):
        raise ValueError("storage_key inválido")
    return value


class MediaListPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, max_length=31)
    amount: int = Field(default=20, ge=1, le=100)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lstrip("@")
        if not USERNAME_RE.match(value):
            raise ValueError("username inválido para o Instagram")
        return value


class MediaDownloadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_pk: str = Field(min_length=1, max_length=64)
    kinds: list[Literal["photo", "video"]] = Field(
        default_factory=lambda: ["photo", "video"], min_length=1, max_length=2
    )

    @field_validator("media_pk")
    @classmethod
    def _media_pk(cls, value: str) -> str:
        value = value.strip()
        if not MEDIA_PK_RE.match(value):
            raise ValueError("media_pk deve conter apenas dígitos")
        return value

    @field_validator("kinds")
    @classmethod
    def _unique_kinds(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class InsightsAccountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountHealthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublishPhotoPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str = Field(min_length=1, max_length=500)
    caption: str = Field(default="", max_length=CAPTION_MAX)

    @field_validator("storage_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _storage_key(value)


class PublishVideoPayload(PublishPhotoPayload):
    thumbnail_key: str | None = Field(default=None, max_length=500)

    @field_validator("thumbnail_key")
    @classmethod
    def _thumbnail(cls, value: str | None) -> str | None:
        return _storage_key(value) if value else None


class PublishReelPayload(PublishVideoPayload):
    pass


class PublishAlbumPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_keys: list[str] = Field(min_length=2, max_length=10)
    caption: str = Field(default="", max_length=CAPTION_MAX)

    @field_validator("storage_keys")
    @classmethod
    def _keys(cls, value: list[str]) -> list[str]:
        keys = [_storage_key(item) for item in value]
        if len(set(keys)) != len(keys):
            raise ValueError("storage_keys duplicados")
        return keys


class PublishStoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str = Field(min_length=1, max_length=500)
    kind: Literal["photo", "video"]
    caption: str = Field(default="", max_length=CAPTION_MAX)

    @field_validator("storage_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _storage_key(value)


JOB_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "media.list": MediaListPayload,
    "media.download": MediaDownloadPayload,
    "insights.account": InsightsAccountPayload,
    "account.health": AccountHealthPayload,
    "publish.photo": PublishPhotoPayload,
    "publish.video": PublishVideoPayload,
    "publish.reel": PublishReelPayload,
    "publish.album": PublishAlbumPayload,
    "publish.story": PublishStoryPayload,
}

JOB_TYPES: frozenset[str] = frozenset(JOB_PAYLOAD_MODELS)
