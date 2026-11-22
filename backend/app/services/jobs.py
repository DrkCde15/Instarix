"""Criação, listagem e cancelamento de jobs."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, conflict, not_found
from app.core.time import utcnow
from app.db.models import IgAccount, IgAccountStatus, Job, JobStatus
from app.jobs.payloads import JOB_PAYLOAD_MODELS, JOB_TYPES
from app.schemas.job import JobCreate
from app.services.quotas import QuotaService


@dataclass(frozen=True)
class JobPageResult:
    items: list[Job]
    has_more: bool


@dataclass(frozen=True)
class JobCreateResult:
    job: Job
    created: bool


class JobService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def _get_account(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID
    ) -> IgAccount:
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

    def _validate_payload(self, job_type: str, payload: dict) -> dict:
        model = JOB_PAYLOAD_MODELS[job_type]
        try:
            return model.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise AppError(
                422,
                "invalid_job_payload",
                f"Payload inválido para o job {job_type}.",
            ) from exc

    def create(
        self,
        tenant_id: uuid.UUID,
        account_id: uuid.UUID,
        data: JobCreate,
        created_by: uuid.UUID | None,
    ) -> JobCreateResult:
        if data.type not in JOB_TYPES:
            raise AppError(
                422,
                "invalid_job_type",
                "Tipo de job desconhecido.",
            )
        payload = self._validate_payload(data.type, data.payload)
        account = self._get_account(tenant_id, account_id)
        if account.status == IgAccountStatus.DISABLED:
            raise conflict("account_disabled", "Conta desativada não aceita jobs.")

        if data.idempotency_key:
            existing = self.db.scalar(
                select(Job).where(
                    Job.tenant_id == tenant_id,
                    Job.idempotency_key == data.idempotency_key,
                )
            )
            if existing is not None:
                return JobCreateResult(existing, created=False)

        QuotaService(self.db, self.settings).check_job(tenant_id)
        now = utcnow()
        job = Job(
            tenant_id=tenant_id,
            account_id=account.id,
            type=data.type,
            payload=payload,
            status=JobStatus.QUEUED,
            priority=data.priority,
            run_after=data.run_after or now,
            created_by=created_by,
            idempotency_key=data.idempotency_key,
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if data.idempotency_key:
                existing = self.db.scalar(
                    select(Job).where(
                        Job.tenant_id == tenant_id,
                        Job.idempotency_key == data.idempotency_key,
                    )
                )
                if existing is not None:
                    return JobCreateResult(existing, created=False)
            raise conflict(
                "job_conflict", "Não foi possível enfileirar o job."
            ) from exc
        return JobCreateResult(job, created=True)

    def get(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        job = self.db.scalar(
            select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        if job is None:
            raise not_found("job_not_found", "Job não encontrado.")
        return job

    def list(
        self,
        tenant_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None,
        status: str | None,
        job_type: str | None,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None,
    ) -> JobPageResult:
        if status is not None and status not in JobStatus.ALL:
            raise AppError(422, "invalid_status", "status inválido.")
        if account_id is not None:
            self._get_account(tenant_id, account_id)

        stmt = select(Job).where(Job.tenant_id == tenant_id)
        if account_id is not None:
            stmt = stmt.where(Job.account_id == account_id)
        if status is not None:
            stmt = stmt.where(Job.status == status)
        if job_type is not None:
            stmt = stmt.where(Job.type == job_type)
        if cursor is not None:
            stmt = stmt.where(
                tuple_(Job.created_at, Job.id) < (cursor[0], cursor[1])
            )
        stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)

        rows = list(self.db.scalars(stmt))
        has_more = len(rows) > limit
        return JobPageResult(items=rows[:limit], has_more=has_more)

    def cancel(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        # FOR UPDATE evita corrida com o claim do worker: se ele já marcou o
        # job como running, o cancelamento espera e enxerga o novo status.
        job = self.db.scalar(
            select(Job)
            .where(Job.id == job_id, Job.tenant_id == tenant_id)
            .with_for_update()
        )
        if job is None:
            raise not_found("job_not_found", "Job não encontrado.")
        if job.status != JobStatus.QUEUED:
            raise conflict(
                "job_not_cancelable",
                "Só é possível cancelar jobs ainda na fila.",
            )
        job.status = JobStatus.CANCELED
        job.finished_at = utcnow()
        self.db.commit()
        return job
