from __future__ import annotations

import logging
import threading
import time

from autopeer.db.session import JobStore
from autopeer.domain.job import JobStatus
from autopeer.services.peer_service import PeerService

LOGGER = logging.getLogger(__name__)


class Worker:
    def __init__(self, store: JobStore, peer_service: PeerService, interval_seconds: float = 1.0):
        self.store = store
        self.peer_service = peer_service
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="autopeer-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self.store.claim_next()
            if job is None:
                time.sleep(self.interval_seconds)
                continue
            try:
                self.store.update(job.id, status=JobStatus.validating)
                result = self.peer_service.execute_peer_job(job.payload)
                self.store.update(job.id, status=JobStatus.succeeded, result=result)
            except Exception as exc:  # noqa: BLE001 - job runner must record arbitrary failures
                LOGGER.exception("job failed", extra={"job_id": job.id})
                self.store.update(job.id, status=JobStatus.failed, error=str(exc))
