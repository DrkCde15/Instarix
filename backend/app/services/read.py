"""Leituras cacheadas: última listagem de mídia e último snapshot."""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.db.models import IgAccount, InsightsSnapshot, Job, JobStatus, MediaAsset
from app.services.storage import MediaStorage


class ReadService:
    def __init__(self, db: Session, storage: MediaStorage) -> None:
        self.db = db
        self.storage = storage

    def _get_account(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> IgAccount:
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

    def latest_media_job(self, tenant_id: uuid.UUID, account_id: uuid.UUID) -> Job:
        self._get_account(tenant_id, account_id)
        job = self.db.scalar(
            select(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.account_id == account_id,
                Job.type == "media.list",
                Job.status == JobStatus.SUCCEEDED,
            )
            .order_by(Job.finished_at.desc(), Job.created_at.desc())
            .limit(1)
        )
        if job is None or not job.result or "items" not in job.result:
            raise AppError(
                409,
                "media_not_cached",
                "Nenhuma listagem de mídia em cache; enfileire um job media.list.",
            )
        return job

    def latest_insights(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID
    ) -> InsightsSnapshot:
        self._get_account(tenant_id, account_id)
        snapshot = self.db.scalar(
            select(InsightsSnapshot)
            .where(
                InsightsSnapshot.tenant_id == tenant_id,
                InsightsSnapshot.account_id == account_id,
            )
            .order_by(InsightsSnapshot.captured_at.desc())
            .limit(1)
        )
        if snapshot is None:
            raise not_found(
                "insights_not_found",
                "Nenhum snapshot de insights; enfileire insights.account.",
            )
        return snapshot

    def media_asset(
        self, tenant_id: uuid.UUID, asset_id: uuid.UUID
    ) -> tuple[MediaAsset, Path]:
        asset = self.db.scalar(
            select(MediaAsset)
            .join(IgAccount, IgAccount.id == MediaAsset.account_id)
            .where(
                MediaAsset.id == asset_id,
                MediaAsset.tenant_id == tenant_id,
                IgAccount.deleted_at.is_(None),
            )
        )
        if asset is None:
            raise not_found("media_not_found", "Mídia não encontrada.")
        try:
            path = self.storage.path(asset.storage_key)
        except ValueError:
            raise not_found("media_not_found", "Mídia não encontrada.") from None
        if not path.is_file():
            raise not_found("media_file_not_found", "Arquivo da mídia não encontrado.")
        return asset, path
