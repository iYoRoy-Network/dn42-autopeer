from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from autopeer.core.config import Settings, get_settings
from autopeer.core.security import Principal, principal_from_dev_headers
from autopeer.services.job_service import JobService
from autopeer.services.metrics_service import MetricsService
from autopeer.services.peer_service import PeerService


def get_current_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Convert the configured auth mechanism into one authorization principal.

    Whether the ASN comes from Kioubit/OIDC session state or the development
    header, every route receives the same Principal object. Admin rights are not
    carried by the identity provider; they are derived from the external
    AUTOPEER__ADMIN_ASNS allowlist so multiple operator ASNs can be configured.
    """
    if settings.auth_mode == "oidc":
        asn = request.session.get("principal_asn")
        if asn is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        try:
            asn = int(asn)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session"
            ) from exc
    else:
        dev_principal = principal_from_dev_headers(request.headers.get("X-Autopeer-ASN"))
        asn = dev_principal.asn

    return Principal(asn=asn, role="admin" if asn in set(settings.admin_asns) else "user")


def get_peer_service(request: Request) -> PeerService:
    return request.app.state.peer_service


def get_job_service(request: Request) -> JobService:
    return request.app.state.job_service


def get_metrics_service(request: Request) -> MetricsService:
    return request.app.state.metrics_service
