from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from autopeer.api.deps import (
    get_current_principal,
    get_job_service,
    get_metrics_service,
    get_peer_service,
)
from autopeer.core.security import Principal
from autopeer.domain.errors import NotFoundError
from autopeer.domain.peer import PeerCreateRequest, PeerPatchRequest
from autopeer.services.job_service import JobService
from autopeer.services.metrics_service import MetricsService
from autopeer.services.peer_service import PeerService

router = APIRouter()


@router.get("/nodes")
async def list_nodes(
    peer_service: PeerService = Depends(get_peer_service),
    metrics: MetricsService = Depends(get_metrics_service),
):
    online_counts = await metrics.online_counts_by_node()
    return [
        node.model_copy(update={"online_peer_count": online_counts.get(node.id)})
        for node in peer_service.list_nodes()
        if node.peering_enabled
    ]


@router.get("/nodes/{node}/peers")
def list_peers(
    node: str,
    principal: Principal = Depends(get_current_principal),
    peer_service: PeerService = Depends(get_peer_service),
):
    return peer_service.list_peers_for_principal(node, principal)


@router.get("/nodes/{node}/peers/{asn}")
def get_peer(
    node: str,
    asn: int,
    principal: Principal = Depends(get_current_principal),
    peer_service: PeerService = Depends(get_peer_service),
):
    try:
        return peer_service.get_peer(node, asn, principal)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/nodes/{node}/peers", status_code=status.HTTP_202_ACCEPTED)
def create_peer(
    node: str,
    request: PeerCreateRequest,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    asn = principal.asn
    payload = {
        "operation": "create",
        "node": node,
        "asn": asn,
        "data": request.model_dump(mode="json"),
    }
    return jobs.enqueue_peer_job(
        kind="create_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )


@router.patch("/nodes/{node}/peers/{asn}", status_code=status.HTTP_202_ACCEPTED)
def update_peer(
    node: str,
    asn: int,
    request: PeerPatchRequest,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    principal.require_peer_access(asn)
    payload = {
        "operation": "update",
        "node": node,
        "asn": asn,
        "data": request.model_dump(mode="json", exclude_unset=True),
    }
    return jobs.enqueue_peer_job(
        kind="update_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )


@router.delete("/nodes/{node}/peers/{asn}", status_code=status.HTTP_202_ACCEPTED)
def delete_peer(
    node: str,
    asn: int,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    principal.require_peer_access(asn)
    payload = {"operation": "delete", "node": node, "asn": asn, "data": {}}
    return jobs.enqueue_peer_job(
        kind="delete_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )
