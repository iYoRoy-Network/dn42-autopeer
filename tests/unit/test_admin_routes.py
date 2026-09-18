import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from autopeer.api.routes.admin import admin_all_peer_status, get_admin_peer
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


class FakeListPeerService:
    def __init__(self, peers_by_node):
        self.peers_by_node = peers_by_node

    def list_nodes(self):
        return [SimpleNamespace(id=node) for node in self.peers_by_node]

    def list_peers_for_principal(self, node, principal):
        return self.peers_by_node[node]


class FakeBatchMetricsService:
    def __init__(self):
        self.calls = []

    def statuses_for_asns(self, asns):
        self.calls.append(set(asns))
        return [{"asn": asn} for asn in sorted(asns)]


def test_admin_all_peer_status_requires_admin():
    metrics = FakeBatchMetricsService()

    with pytest.raises(HTTPException) as exc_info:
        admin_all_peer_status(Principal(asn=4242420002), FakeListPeerService({}), metrics)

    assert exc_info.value.status_code == 403
    assert metrics.calls == []


def test_admin_all_peer_status_collects_asns_and_delegates():
    principal = Principal(asn=4242420001, role="admin")
    peers = FakeListPeerService(
        {
            "fra01": [SimpleNamespace(asn=4242420002), SimpleNamespace(asn=4242420003)],
            "hkg01": [SimpleNamespace(asn=4242420002)],
        }
    )
    metrics = FakeBatchMetricsService()

    result = admin_all_peer_status(principal, peers, metrics)

    assert metrics.calls == [{4242420002, 4242420003}]
    assert [item["asn"] for item in result] == [4242420002, 4242420003]
