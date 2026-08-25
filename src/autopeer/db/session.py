from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from autopeer.domain.job import JobRecord, JobStatus


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Small durable queue backed by SQLite.

    SQLite is runtime state only: it remembers requested jobs and their status,
    while the network source of truth remains the Ansible Git repository.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by_asn INTEGER NOT NULL,
                    node TEXT,
                    peer_asn INTEGER,
                    payload TEXT NOT NULL,
                    result TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create(
        self,
        *,
        kind: str,
        requested_by_asn: int,
        node: str | None,
        peer_asn: int | None,
        payload: dict[str, Any],
    ) -> JobRecord:
        job_id = f"job_{uuid4().hex}"
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO jobs (id, kind, status, requested_by_asn, node, peer_asn, payload, result, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    kind,
                    JobStatus.queued.value,
                    requested_by_asn,
                    node,
                    peer_asn,
                    json.dumps(payload),
                    "{}",
                    None,
                    now,
                    now,
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> JobRecord:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row_to_record(row)

    def claim_next(self) -> JobRecord | None:
        with self.connect() as conn:
            # BEGIN IMMEDIATE takes SQLite's write lock before selecting so two
            # API processes cannot claim the same queued job at the same time.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1",
                (JobStatus.queued.value,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            now = utcnow()
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (JobStatus.running.value, now, row["id"]),
            )
            conn.execute("COMMIT")
        return self.get(row["id"])

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobRecord:
        current = self.get(job_id)
        new_status = status or current.status
        new_result = current.result if result is None else result
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, updated_at = ? WHERE id = ?",
                (new_status.value, json.dumps(new_result), error, now, job_id),
            )
        return self.get(job_id)

    def _row_to_record(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            kind=row["kind"],
            status=row["status"],
            requested_by_asn=row["requested_by_asn"],
            node=row["node"],
            peer_asn=row["peer_asn"],
            payload=json.loads(row["payload"]),
            result=json.loads(row["result"]),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
