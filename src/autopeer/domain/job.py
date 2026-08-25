from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    validating = "validating"
    committing = "committing"
    applying = "applying"
    succeeded = "succeeded"
    failed = "failed"


class JobRecord(BaseModel):
    id: str
    kind: str
    status: JobStatus
    requested_by_asn: int
    node: str | None = None
    peer_asn: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
