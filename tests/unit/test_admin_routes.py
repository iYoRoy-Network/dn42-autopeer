import pytest
from fastapi import HTTPException

from autopeer.api.routes.admin import get_admin_peer
from autopeer.core.security import Principal
from autopeer.domain.errors import NotFoundError


class FakePeerService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def get_peer(self, node, asn, principal):
        self.calls.append((node, asn, principal))
        if self.error is not None:
            raise self.error
        return self.result


def test_get_admin_peer_requires_admin():
    service = FakePeerService(result={"asn": 4242420001})

    with pytest.raises(HTTPException) as exc_info:
        get_admin_peer("fra01", 4242420001, Principal(asn=4242420002), service)

    assert exc_info.value.status_code == 403
    assert service.calls == []


def test_get_admin_peer_delegates_to_service():
    principal = Principal(asn=4242420002, role="admin")
    service = FakePeerService(result={"asn": 4242420001})

    result = get_admin_peer("fra01", 4242420001, principal, service)

    assert result == {"asn": 4242420001}
    assert service.calls == [("fra01", 4242420001, principal)]


def test_get_admin_peer_maps_not_found_to_404():
    service = FakePeerService(error=NotFoundError("peer not found"))

    with pytest.raises(HTTPException) as exc_info:
        get_admin_peer("fra01", 4242420001, Principal(asn=1, role="admin"), service)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "peer not found"
