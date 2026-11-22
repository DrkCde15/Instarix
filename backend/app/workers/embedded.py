"""Worker embutido no processo da API (desenvolvimento local).

Em produção o worker roda como processo separado. Esta classe existe para que
um único ``uvicorn`` consiga processar a fila durante o desenvolvimento, sem
duplicar jobs: a serialização por conta continua sendo feita pelo banco.
"""

import logging
import threading
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.crypto import get_cipher
from app.services.ig_gateway import get_ig_gateway
from app.workers.worker import build_worker

logger = logging.getLogger(__name__)


class EmbeddedWorker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if not self.settings.embedded_worker_enabled or self._threads:
            return

        threads = self.settings.job_worker_threads
        if threads < 1:
            raise RuntimeError("JOB_WORKER_THREADS deve ser >= 1")

        cipher = get_cipher()
        gateway = get_ig_gateway()
        for index in range(threads):
            worker = build_worker(index, self.settings, cipher, gateway)
            thread = threading.Thread(
                target=worker.run_forever,
                args=(self._stop,),
                name=f"instarix-embedded-worker-{index}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

        logger.info(
            "embedded_worker_started threads=%s media_root=%s",
            threads,
            Path(self.settings.media_storage_dir).resolve(),
        )

    def shutdown(self) -> None:
        if not self._threads:
            return
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=self.settings.job_poll_interval_seconds + 5)
        logger.info("embedded_worker_stopped")
