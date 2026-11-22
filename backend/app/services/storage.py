"""Storage local de mídia (S3 fica para a fase 4).

A API e o worker compartilham o mesmo diretório/volume. Os caminhos são sempre
resolvidos dentro da raiz configurada para impedir path traversal.
"""

import shutil
from pathlib import Path
from typing import Protocol

from app.core.config import Settings, get_settings

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class MediaStorage(Protocol):
    def save(self, source: Path, key: str) -> int: ...

    def save_bytes(self, data: bytes, key: str) -> int: ...

    def path(self, key: str) -> Path: ...


class LocalMediaStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("storage_key inválido")
        return candidate

    def save(self, source: Path, key: str) -> int:
        destination = self._safe_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination.stat().st_size

    def save_bytes(self, data: bytes, key: str) -> int:
        destination = self._safe_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return len(data)

    def path(self, key: str) -> Path:
        return self._safe_path(key)


def get_media_storage() -> MediaStorage:
    return LocalMediaStorage(get_settings().media_storage_dir)


def build_media_storage(settings: Settings) -> MediaStorage:
    return LocalMediaStorage(settings.media_storage_dir)
