from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from autopeer.api.deps import (
    get_current_principal,
    get_job_service,
    get_metrics_service,
    get_peer_service,
)
from autopeer.core.security import Principal
from autopeer.domain.peer import PeerCreateRequest, PeerPatchRequest
from autopeer.services.job_service import JobService
from autopeer.services.metrics_service import MetricsService
from autopeer.services.peer_service import PeerService

router = APIRouter()


def require_admin(principal: Principal) -> None:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")


@router.get("/admin/nodes")
async def list_admin_nodes(
    principal: Principal = Depends(get_current_principal),
    peer_service: PeerService = Depends(get_peer_service),
    metrics: MetricsService = Depends(get_metrics_service),
):
    require_admin(principal)
    online_counts = metrics.online_counts_by_node()
    runtime_metrics = metrics.node_metrics_by_node()
    return [
        node.model_copy(
            update={
                "online_peer_count": online_counts.get(node.id),
                "runtime_metrics": runtime_metrics.get(node.id),
            }
        )
        for node in peer_service.list_nodes()
    ]


@router.get("/admin/nodes/{node}/peers")
def list_admin_peers(
    node: str,
    principal: Principal = Depends(get_current_principal),
    peer_service: PeerService = Depends(get_peer_service),
):
    require_admin(principal)
    return peer_service.list_peers_for_principal(node, principal)


@router.post("/admin/nodes/{node}/peers/{asn}", status_code=status.HTTP_202_ACCEPTED)
def create_admin_peer(
    node: str,
    asn: int,
    request: PeerCreateRequest,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    require_admin(principal)
    payload = {
        "operation": "create",
        "node": node,
        "asn": asn,
        "data": request.model_dump(mode="json"),
    }
    return jobs.enqueue_peer_job(
        kind="create_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )


@router.patch("/admin/nodes/{node}/peers/{asn}", status_code=status.HTTP_202_ACCEPTED)
def update_admin_peer(
    node: str,
    asn: int,
    request: PeerPatchRequest,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    require_admin(principal)
    payload = {
        "operation": "update",
        "node": node,
        "asn": asn,
        "data": request.model_dump(mode="json", exclude_unset=True),
    }
    return jobs.enqueue_peer_job(
        kind="update_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )


@router.delete("/admin/nodes/{node}/peers/{asn}", status_code=status.HTTP_202_ACCEPTED)
def delete_admin_peer(
    node: str,
    asn: int,
    principal: Principal = Depends(get_current_principal),
    jobs: JobService = Depends(get_job_service),
):
    require_admin(principal)
    payload = {"operation": "delete", "node": node, "asn": asn, "data": {}}
    return jobs.enqueue_peer_job(
        kind="delete_peer", requested_by_asn=principal.asn, node=node, peer_asn=asn, payload=payload
    )
