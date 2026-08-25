from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass(frozen=True)
class Principal:
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
