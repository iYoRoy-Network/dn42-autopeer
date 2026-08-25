from __future__ import annotations

from fastapi import APIRouter, Depends

from autopeer.api.deps import get_current_principal, get_metrics_service
from autopeer.core.security import Principal
from autopeer.services.metrics_service import MetricsService

router = APIRouter()


@router.get("/me/peers/status")
async def my_peer_status(
    principal: Principal = Depends(get_current_principal),
    metrics: MetricsService = Depends(get_metrics_service),
):
    return await metrics.status_for_asn(principal.asn)
