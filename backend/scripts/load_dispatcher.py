"""Teste de carga do claim/dispatcher contra o banco configurado.

Cria jobs diretamente (sem passar pela API/quota) e dispara vários workers
concorrentes apenas para exercitar ``JobWorker.claim()``; cada job reivindicado
é marcado como ``succeeded`` em seguida. O objetivo é medir throughput de claim
e detectar job duplicado, não executar chamadas ao Instagram.

Use em Postgres. Em SQLite o lock é global e o resultado não representa produção.

Exemplo:
    python -m scripts.load_dispatcher \
      --tenant-id <uuid> --account-id <uuid> --jobs 200 --workers 4
"""

import argparse
import threading
import uuid
from collections import Counter

from sqlalchemy import delete, update
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.models import Job, JobStatus
from app.db.session import get_engine
from app.workers.worker import JobWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga do claim de jobs")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--account-id", required=True, action="append")
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.jobs < 1 or args.workers < 1:
        parser.error("--jobs e --workers devem ser >= 1")

    settings = get_settings()
    engine = get_engine()
    session_factory = sessionmaker(engine, expire_on_commit=False)
    job_ids: list[uuid.UUID] = []

    with session_factory() as db:
        for index in range(args.jobs):
            job = Job(
                tenant_id=args.tenant_id,
                type="media.list",
                payload={},
                status=JobStatus.QUEUED,
                run_after=utcnow(),
            )
            # Distribui entre as contas informadas.
            job.account_id = args.account_id[index % len(args.account_id)]
            db.add(job)
            db.flush()
            job_ids.append(job.id)
        db.commit()

    claimed: Counter[uuid.UUID] = Counter()
    lock = threading.Lock()

    def run_worker(worker_id: str) -> None:
        worker = JobWorker(
            session_factory=session_factory,
            cipher=object(),  # type: ignore[arg-type]
            gateway=object(),  # type: ignore[arg-type]
            storage=object(),  # type: ignore[arg-type]
            settings=settings,
            worker_id=worker_id,
        )
        while True:
            job = worker.claim()
            if job is None:
                return
            with lock:
                claimed[job.id] += 1
            with session_factory() as db:
                db.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status=JobStatus.SUCCEEDED,
                        locked_by=None,
                        locked_at=None,
                        finished_at=utcnow(),
                    )
                )
                db.commit()

    threads = [
        threading.Thread(target=run_worker, args=(f"load-{index}",))
        for index in range(args.workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    duplicates = sum(1 for count in claimed.values() if count > 1)
    missing = args.jobs - len(claimed)
    print(
        f"jobs={args.jobs} claimed={sum(claimed.values())} unique={len(claimed)} "
        f"duplicates={duplicates} missing={missing} workers={args.workers}"
    )

    if args.cleanup:
        with session_factory() as db:
            db.execute(delete(Job).where(Job.id.in_(job_ids)))
            db.commit()

    return 0 if duplicates == 0 and missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
