"""Métricas em formato Prometheus, calculadas a partir do banco."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IgAccount, Job, JobStatus, WebhookDelivery, WebhookStatus


def _lines(name: str, help_text: str, rows, label: str) -> list[str]:
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    for value, count in rows:
        lines.append(f'{name}{{{label}="{value}"}} {int(count)}')
    return lines


def collect_metrics(db: Session, tenant_id: uuid.UUID) -> str:
    jobs = db.execute(
        select(Job.type, Job.status, func.count(Job.id))
        .where(Job.tenant_id == tenant_id)
        .group_by(Job.type, Job.status)
    ).all()
    queue = db.execute(
        select(Job.priority, func.count(Job.id))
        .where(Job.tenant_id == tenant_id, Job.status == JobStatus.QUEUED)
        .group_by(Job.priority)
    ).all()
    accounts = db.execute(
        select(IgAccount.status, func.count(IgAccount.id))
        .where(IgAccount.tenant_id == tenant_id)
        .group_by(IgAccount.status)
    ).all()
    webhooks = db.execute(
        select(WebhookDelivery.status, func.count(WebhookDelivery.id))
        .where(WebhookDelivery.tenant_id == tenant_id)
        .group_by(WebhookDelivery.status)
    ).all()

    lines: list[str] = []
    lines += [
        "# HELP jobs_total Jobs por tipo e status.",
        "# TYPE jobs_total gauge",
    ]
    for job_type, status, count in jobs:
        lines.append(
            f'jobs_total{{type="{job_type}",status="{status}"}} {int(count)}'
        )
    lines += _lines(
        "queue_depth", "Jobs na fila por prioridade.", queue, "priority"
    )
    lines += _lines(
        "accounts_by_status", "Contas por status.", accounts, "status"
    )
    lines += _lines(
        "webhook_deliveries", "Entregas de webhook por status.", webhooks, "status"
    )
    failed = sum(int(count) for status, count in webhooks if status == WebhookStatus.FAILED)
    pending = sum(
        int(count) for status, count in webhooks if status == WebhookStatus.PENDING
    )
    lines += [
        "# HELP webhook_delivery_failures_total Entregas de webhook falhas.",
        "# TYPE webhook_delivery_failures_total gauge",
        f"webhook_delivery_failures_total {failed}",
        "# HELP webhook_delivery_pending Entregas de webhook pendentes.",
        "# TYPE webhook_delivery_pending gauge",
        f"webhook_delivery_pending {pending}",
    ]
    return "\n".join(lines) + "\n"
