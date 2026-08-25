from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from autopeer.api.deps import get_current_principal, get_job_service
from autopeer.core.security import Principal
from autopeer.services.job_service import JobService

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    try:
        job = jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if not principal.is_admin and job.requested_by_asn != principal.asn:
        raise HTTPException(status_code=403, detail="job is not owned by current principal")
    return job
