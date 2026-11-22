"""Quotas por plano do tenant."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, not_found
from app.core.time import utcnow
from app.db.models import IgAccount, Job, Tenant


@dataclass(frozen=True)
class PlanLimits:
    accounts: int
    jobs_per_day: int


@dataclass(frozen=True)
class Usage:
    plan: str
    accounts_used: int
    accounts_limit: int
    jobs_today_used: int
    jobs_today_limit: int


class QuotaService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def limits_for(self, plan: str) -> PlanLimits:
        if plan == "pro":
            return PlanLimits(
                self.settings.quota_pro_accounts,
                self.settings.quota_pro_jobs_per_day,
            )
        if plan == "enterprise":
            return PlanLimits(0, 0)
        return PlanLimits(
            self.settings.quota_free_accounts,
            self.settings.quota_free_jobs_per_day,
        )

    def _tenant(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise not_found("tenant_not_found", "Tenant não encontrado.")
        return tenant

    def _accounts_used(self, tenant_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count(IgAccount.id)).where(
                    IgAccount.tenant_id == tenant_id,
                    IgAccount.deleted_at.is_(None),
                )
            )
            or 0
        )

    def _jobs_today_used(self, tenant_id: uuid.UUID) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return int(
            self.db.scalar(
                select(func.count(Job.id)).where(
                    Job.tenant_id == tenant_id,
                    Job.created_at >= start,
                )
            )
            or 0
        )

    def usage(self, tenant_id: uuid.UUID) -> Usage:
        tenant = self._tenant(tenant_id)
        limits = self.limits_for(tenant.plan)
        return Usage(
            plan=tenant.plan,
            accounts_used=self._accounts_used(tenant_id),
            accounts_limit=limits.accounts,
            jobs_today_used=self._jobs_today_used(tenant_id),
            jobs_today_limit=limits.jobs_per_day,
        )

    def check_account(self, tenant_id: uuid.UUID) -> None:
        tenant = self._tenant(tenant_id)
        limits = self.limits_for(tenant.plan)
        if limits.accounts <= 0:
            return
        used = self._accounts_used(tenant_id)
        if used >= limits.accounts:
            raise AppError(
                429,
                "quota_exceeded",
                f"O plano {tenant.plan} permite no máximo {limits.accounts} contas.",
            )

    def check_job(self, tenant_id: uuid.UUID) -> None:
        tenant = self._tenant(tenant_id)
        limits = self.limits_for(tenant.plan)
        if limits.jobs_per_day <= 0:
            return
        used = self._jobs_today_used(tenant_id)
        if used >= limits.jobs_per_day:
            raise AppError(
                429,
                "quota_exceeded",
                f"O plano {tenant.plan} permite no máximo "
                f"{limits.jobs_per_day} jobs por dia.",
            )
