from __future__ import annotations

from typing import Any

from autopeer.db.session import JobStore
from autopeer.domain.job import JobRecord


class JobService:
    def __init__(self, store: JobStore):
        self.store = store

    def enqueue_peer_job(
        self, *, kind: str, requested_by_asn: int, node: str, peer_asn: int, payload: dict[str, Any]
    ) -> JobRecord:
        return self.store.create(
            kind=kind,
            requested_by_asn=requested_by_asn,
            node=node,
            peer_asn=peer_asn,
            payload=payload,
        )

    def get(self, job_id: str) -> JobRecord:
        return self.store.get(job_id)
