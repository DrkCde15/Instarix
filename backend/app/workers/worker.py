"""Worker da fila de jobs.

O Postgres é a fila: cada worker faz ``SELECT ... FOR UPDATE SKIP LOCKED`` de
um job ``queued`` cuja conta não tenha outro job ``running``. O índice único
parcial ``uq_jobs_account_running`` é a garantia final de que a mesma conta
nunca roda dois jobs ao mesmo tempo, mesmo com vários workers.

Uso:
    python -m app.workers.worker             # loop com N threads
    python -m app.workers.worker --once      # sweeper + processa a fila atual
"""

import argparse
import logging
import os
import random
import signal
import socket
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from app.core.config import Settings, get_settings
from app.core.crypto import Cipher, get_cipher
from app.core.logging import configure_logging
from app.core.time import utcnow
from app.db.models import IgAccount, IgAccountStatus, Job, JobStatus
from app.db.session import get_engine
from app.jobs.handlers import HANDLERS, JobContext, JobError
from app.jobs.payloads import JOB_PAYLOAD_MODELS
from app.services.ig_gateway import IgGateway, get_ig_gateway
from app.services.storage import MediaStorage, build_media_storage
from app.services.webhooks import (
    HttpWebhookNotifier,
    WebhookNotifier,
    WebhookService,
)

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        cipher: Cipher,
        gateway: IgGateway,
        storage: MediaStorage,
        settings: Settings,
        worker_id: str,
        webhook_notifier: WebhookNotifier | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.cipher = cipher
        self.gateway = gateway
        self.storage = storage
        self.settings = settings
        self.worker_id = worker_id
        self.webhook_notifier = webhook_notifier or HttpWebhookNotifier()

    def claim(self) -> Job | None:
        now = utcnow()
        with self.session_factory() as db:
            outer = aliased(Job)
            inner = aliased(Job)
            # Subquery correlacionada: não pegar job de conta que já tem um
            # running. O índice parcial continua sendo a garantia final.
            busy = (
                select(inner.id)
                .where(
                    inner.account_id == outer.account_id,
                    inner.status == JobStatus.RUNNING,
                )
                .exists()
            )
            stmt = (
                select(outer)
                .where(
                    outer.status == JobStatus.QUEUED,
                    outer.run_after <= now,
                    ~busy,
                )
                .order_by(
                    outer.priority.asc(), outer.run_after.asc(), outer.created_at.asc()
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = db.scalar(stmt)
            if job is None:
                return None

            job.status = JobStatus.RUNNING
            job.locked_by = self.worker_id
            job.locked_at = now
            job.started_at = now
            job.attempts += 1
            job.error_code = None
            job.error_message = None
            try:
                db.commit()
            except IntegrityError:
                # Outro worker pegou um job da mesma conta entre o select e o
                # commit; o índice parcial rejeitou. Tenta na próxima rodada.
                db.rollback()
                logger.info("job_claim_conflict worker_id=%s", self.worker_id)
                return None
            return job

    def execute(self, job_id: uuid.UUID) -> bool:
        with self.session_factory() as db:
            job = db.get(Job, job_id)
            if (
                job is None
                or job.status != JobStatus.RUNNING
                or job.locked_by != self.worker_id
            ):
                return False

            account = db.get(IgAccount, job.account_id) if job.account_id else None
            if account is None:
                self._fail(
                    db,
                    job,
                    None,
                    JobError("account_not_found", "Conta do job não existe."),
                )
                return True
            if account.deleted_at is not None or account.status == IgAccountStatus.DISABLED:
                self._fail(
                    db,
                    job,
                    account,
                    JobError("account_disabled", "Conta desativada; job recusado."),
                )
                return True

            handler = HANDLERS.get(job.type)
            if handler is None:
                self._fail(
                    db,
                    job,
                    account,
                    JobError("invalid_job_type", "Tipo de job desconhecido."),
                )
                return True

            try:
                payload_model = JOB_PAYLOAD_MODELS[job.type]
                payload_model.model_validate(job.payload)
            except ValidationError as exc:
                self._fail(
                    db,
                    job,
                    account,
                    JobError(
                        "invalid_job_payload",
                        "O payload gravado não corresponde ao tipo do job.",
                    ),
                )
                logger.warning(
                    "job_payload_invalid job_id=%s type=%s errors=%s",
                    job.id,
                    job.type,
                    exc.errors(include_url=False),
                )
                return True

            context = JobContext(
                db=db,
                job=job,
                account=account,
                cipher=self.cipher,
                gateway=self.gateway,
                storage=self.storage,
            )
            try:
                result = handler(context)
            except JobError as exc:
                self._fail(db, job, account, exc)
            except Exception:  # noqa: BLE001 - bug do handler vira retry sanitizado
                logger.exception(
                    "job_handler_crashed job_id=%s type=%s", job.id, job.type
                )
                self._fail(
                    db,
                    job,
                    account,
                    JobError(
                        "job_internal_error",
                        "Erro interno ao executar o job.",
                        retryable=True,
                    ),
                )
            else:
                job.status = JobStatus.SUCCEEDED
                job.result = result
                job.error_code = None
                job.error_message = None
                job.locked_by = None
                job.locked_at = None
                job.finished_at = utcnow()
                self._enqueue_job_event(db, job, "job.succeeded")
                db.commit()
                logger.info(
                    "job_succeeded job_id=%s type=%s account_id=%s",
                    job.id,
                    job.type,
                    account.id,
                )
            return True

    def _fail(
        self,
        db: Session,
        job: Job,
        account: IgAccount | None,
        error: JobError,
    ) -> None:
        now = utcnow()
        if account is not None:
            if error.account_status is not None:
                account.status = error.account_status
            if error.clear_session:
                account.session_enc = None
            account.last_error_code = error.code
            account.last_error_message = error.message

        job.error_code = error.code
        job.error_message = error.message[:500]
        job.locked_by = None
        job.locked_at = None

        if error.retryable and job.attempts < job.max_attempts:
            delay = self.settings.job_backoff_base_seconds * (
                2 ** max(0, job.attempts - 1)
            ) + random.uniform(0, 1)
            job.status = JobStatus.QUEUED
            job.run_after = now + timedelta(seconds=delay)
            logger.warning(
                "job_retry_scheduled job_id=%s type=%s attempt=%s/%s delay=%.1fs",
                job.id,
                job.type,
                job.attempts,
                job.max_attempts,
                delay,
            )
        else:
            job.status = JobStatus.FAILED
            job.finished_at = now
            self._enqueue_job_event(db, job, "job.failed")
            logger.warning(
                "job_failed job_id=%s type=%s code=%s attempt=%s/%s",
                job.id,
                job.type,
                error.code,
                job.attempts,
                job.max_attempts,
            )
        db.commit()

    def _enqueue_job_event(self, db: Session, job: Job, event: str) -> None:
        payload = {
            "job_id": str(job.id),
            "account_id": str(job.account_id) if job.account_id else None,
            "type": job.type,
            "status": job.status,
            "error_code": job.error_code,
        }
        try:
            with db.begin_nested():
                WebhookService(db, self.cipher, self.settings).enqueue_event(
                    job.tenant_id, event, payload
                )
        except Exception:  # noqa: BLE001 - webhook não pode derrubar o job
            logger.exception("webhook_enqueue_failed job_id=%s event=%s", job.id, event)

    def deliver_webhooks(self, limit: int = 20) -> int:
        with self.session_factory() as db:
            return WebhookService(db, self.cipher, self.settings).deliver_due(
                self.webhook_notifier, limit=limit
            )

    def sweep(self) -> int:
        """Recupera jobs running cujo worker morreu (lock antigo)."""
        cutoff = utcnow() - timedelta(seconds=self.settings.job_lock_timeout_seconds)
        with self.session_factory() as db:
            jobs = list(
                db.scalars(
                    select(Job)
                    .where(
                        Job.status == JobStatus.RUNNING,
                        Job.locked_at.is_not(None),
                        Job.locked_at < cutoff,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for job in jobs:
                job.locked_by = None
                job.locked_at = None
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.QUEUED
                    job.run_after = utcnow()
                    job.error_code = "job_worker_lost"
                    job.error_message = "O worker interrompeu o job; será repetido."
                    logger.warning(
                        "job_recovered job_id=%s attempt=%s/%s",
                        job.id,
                        job.attempts,
                        job.max_attempts,
                    )
                else:
                    job.status = JobStatus.FAILED
                    job.finished_at = utcnow()
                    job.error_code = "job_worker_lost"
                    job.error_message = "O worker interrompeu o job."
                    logger.warning("job_lost job_id=%s", job.id)
            if jobs:
                db.commit()
            return len(jobs)

    def run_available(
        self, limit: int = 100, stop: threading.Event | None = None
    ) -> int:
        processed = 0
        while processed < limit:
            if stop is not None and stop.is_set():
                break
            job = self.claim()
            if job is None:
                break
            self.execute(job.id)
            processed += 1
        return processed

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.sweep()
                self.deliver_webhooks()
                processed = self.run_available(limit=50, stop=stop)
                if processed == 0:
                    stop.wait(self.settings.job_poll_interval_seconds)
            except Exception:  # noqa: BLE001 - mantém o worker vivo
                logger.exception("worker_loop_error worker_id=%s", self.worker_id)
                stop.wait(self.settings.job_poll_interval_seconds)


def _worker_id(index: int = 0) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{index}:{uuid.uuid4().hex[:8]}"


def build_worker(
    index: int, settings: Settings, cipher: Cipher, gateway: IgGateway
) -> JobWorker:
    return JobWorker(
        session_factory=sessionmaker(get_engine(), expire_on_commit=False),
        cipher=cipher,
        gateway=gateway,
        storage=build_media_storage(settings),
        settings=settings,
        worker_id=_worker_id(index),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker de jobs do Instarix")
    parser.add_argument(
        "--once",
        action="store_true",
        help="executa o sweeper e processa a fila disponível, sem loop",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="threads concorrentes (padrão: JOB_WORKER_THREADS)",
    )
    args = parser.parse_args(argv)

    configure_logging()
    settings = get_settings()
    cipher = get_cipher()
    gateway = get_ig_gateway()

    if args.once:
        worker = build_worker(0, settings, cipher, gateway)
        swept = worker.sweep()
        processed = worker.run_available(limit=1000)
        delivered = worker.deliver_webhooks(limit=1000)
        logger.info(
            "worker_once_finished swept=%s processed=%s delivered=%s",
            swept,
            processed,
            delivered,
        )
        return 0

    threads = args.threads or settings.job_worker_threads
    if threads < 1:
        parser.error("--threads deve ser >= 1")

    stop = threading.Event()

    def _stop(signum, _frame):
        logger.info("worker_stopping signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    workers = [
        build_worker(index, settings, cipher, gateway)
        for index in range(threads)
    ]
    threads_handle = [
        threading.Thread(
            target=worker.run_forever,
            args=(stop,),
            name=f"instarix-worker-{index}",
            daemon=True,
        )
        for index, worker in enumerate(workers)
    ]
    for thread in threads_handle:
        thread.start()
    logger.info(
        "worker_started threads=%s media_root=%s",
        threads,
        Path(settings.media_storage_dir).resolve(),
    )
    for thread in threads_handle:
        thread.join()
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
