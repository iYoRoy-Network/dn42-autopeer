from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass(frozen=True)
class Principal:
    """Authenticated actor used by services and routes.

    The MVP identity model is intentionally ASN-centric: normal users can only
    mutate their own ASN's peer file, while ASNs listed in AUTOPEER__ADMIN_ASNS
    receive the admin role and may operate across peer ASNs.
    """

    asn: int
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def require_peer_access(self, peer_asn: int) -> None:
        if not self.is_admin and self.asn != peer_asn:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="peer ASN is not owned by current principal",
            )


def principal_from_dev_headers(x_autopeer_asn: str | None) -> Principal:
    """Development-only identity source for local testing or a trusted reverse proxy."""
    if not x_autopeer_asn:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Autopeer-ASN development auth header",
        )
    try:
        asn = int(x_autopeer_asn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid ASN header") from exc
    return Principal(asn=asn)
