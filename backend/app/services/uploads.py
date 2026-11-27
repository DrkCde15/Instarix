"""Upload local de mídia para os jobs de publicação.

O plano original usa S3/MinIO com URL pré-assinada. Nesta fase o storage é
local (mesmo volume do worker), então o upload é multipart direto na API e o
job recebe apenas o ``storage_key``.
"""

import uuid

from app.core.config import Settings
from app.core.errors import AppError
from app.services.storage import MediaStorage

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
CANONICAL_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


def _matches_signature(content_type: str, data: bytes) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type in VIDEO_TYPES:
        return len(data) >= 12 and data[4:8] == b"ftyp"
    return False


class UploadService:
    def __init__(self, storage: MediaStorage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings

    def save(
        self,
        tenant_id: uuid.UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str, int]:
        content_type = (content_type or "").split(";")[0].strip().lower()
        if content_type not in CANONICAL_SUFFIX:
            raise AppError(
                422,
                "invalid_upload_type",
                "Envie uma imagem JPEG/PNG/WebP ou um vídeo MP4/MOV.",
            )
        if not data:
            raise AppError(422, "empty_upload", "O arquivo enviado está vazio.")
        if len(data) > self.settings.upload_max_bytes:
            raise AppError(
                413,
                "upload_too_large",
                f"O arquivo excede o limite de {self.settings.upload_max_bytes} bytes.",
            )
        if not _matches_signature(content_type, data):
            raise AppError(
                422,
                "invalid_upload_content",
                "O conteúdo do arquivo não corresponde ao tipo informado.",
            )

        # A extensão vem do tipo validado, nunca do nome enviado pelo cliente.
        suffix = CANONICAL_SUFFIX[content_type]

        key = f"uploads/{tenant_id}/{uuid.uuid4().hex}{suffix}"
        size = self.storage.save_bytes(data, key)
        return key, content_type, size
