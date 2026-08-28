from pathlib import Path

import pytest

from autopeer.adapters.repository import ConfigRepository, dump_yaml
from autopeer.domain.node import NodePeeringMetadata
from autopeer.domain.peer import BgpTransport, BgpTransportMode


def build_repository(
    tmp_path: Path, *, peering: dict, dn42: dict | None = None
) -> ConfigRepository:
    dump_yaml(
        tmp_path / "ansible" / "inventory.yml",
        {"bird_nodes": {"hosts": {"test01": None}}},
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "main.yml",
        {"node": {"name": "test01", "peering": peering}},
    )
    if dn42 is not None:
        dump_yaml(
            tmp_path / "ansible" / "host_vars" / "test01" / "bird-dn42.yml",
            {"dn42": dn42},
        )
    return ConfigRepository(tmp_path)


def test_display_metadata_is_parsed():
    metadata = NodePeeringMetadata.from_yaml(
        {
            "display_name": "Example node",
            "subtitle": "A short description",
            "protocol_stack": "ipv4",
        }
    )

    assert metadata.display_name == "Example node"
    assert metadata.subtitle == "A short description"
    assert metadata.protocol_stack == "ipv4"


def test_empty_endpoint_public_key_and_exporters_are_unset():
    metadata = NodePeeringMetadata.from_yaml(
        {
            "endpoint": None,
            "publickey": None,
            "exporters": {"bird": None, "wireguard": "", "node": None},
        }
    )

    assert metadata.endpoint is None
    assert metadata.publickey is None
    assert metadata.exporters == {}


def test_nested_range_policy_is_normalized():
    metadata = NodePeeringMetadata.from_yaml(
        {
            "listen_port_policy": {
                "mode": "range",
                "range": {"min": 52000, "max": 52999},
            }
        }
    )

    assert metadata.listen_port_policy.port_min == 52000
    assert metadata.listen_port_policy.port_max == 52999


def test_repository_counts_peer_files_and_allocates_first_free_port(tmp_path: Path):
    repo = build_repository(
        tmp_path,
        peering={
            "enabled": True,
            "listen_port_policy": {
                "mode": "range",
                "range": {"min": 52000, "max": 52002},
            },
        },
    )
    repo.write_peer(
        "test01",
        4242420001,
        {"wireguard": {"listen_port": 52000}},
    )

    summary = repo.list_nodes()[0]

    assert summary.peer_count == 1
    assert repo.allocated_listen_port("test01", 4242420002) == 52001


def test_repository_preserves_existing_listen_port(tmp_path: Path):
    repo = build_repository(
        tmp_path,
        peering={
            "listen_port_policy": {
                "mode": "range",
                "range": {"min": 52000, "max": 52002},
            }
        },
    )

    existing = {"wireguard": {"listen_port": 52002}}

    assert repo.allocated_listen_port("test01", 4242420001, existing) == 52002


def test_peer_response_uses_persisted_port_for_legacy_asn(tmp_path: Path):
    repo = build_repository(
        tmp_path,
        peering={"listen_port_policy": {"mode": "asn_suffix"}},
    )
    peer = {
        "asn": 4201273722,
        "wireguard": {
            "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "listen_port": 33722,
            "endpoint": "legacy.example:33722",
        },
        "lla": "fe80::1",
        "bgp": {"extended_next_hop": True},
    }

    response = repo.peer_to_response("test01", 4201273722, peer)

    assert response.listen_port == 33722
    assert response.connection_info is not None
    assert response.connection_info.listen_port == 33722


def test_repository_reports_exhausted_port_range(tmp_path: Path):
    repo = build_repository(
        tmp_path,
        peering={
            "listen_port_policy": {
                "mode": "range",
                "range": {"min": 52000, "max": 52000},
            }
        },
    )
    repo.write_peer(
        "test01",
        4242420001,
        {"wireguard": {"listen_port": 52000}},
    )

    with pytest.raises(ValueError, match="no free listen port"):
        repo.allocated_listen_port("test01", 4242420002)


@pytest.mark.parametrize(
    ("mode", "remote_address", "expected"),
    [
        (BgpTransportMode.ipv6_link_local, "fe80::1", "fe80::2024"),
        (BgpTransportMode.ipv4, "172.20.0.2", "172.20.0.1"),
        (BgpTransportMode.ipv6, "fd00::2", "fd00::1"),
    ],
)
def test_connection_info_returns_local_bgp_address(
    tmp_path: Path,
    mode: BgpTransportMode,
    remote_address: str,
    expected: str,
):
    repo = build_repository(
        tmp_path,
        peering={"listen_port_policy": {"mode": "asn_suffix"}},
        dn42={"own_ip": "172.20.0.1", "own_ipv6": "fd00::1"},
    )

    info = repo.connection_info(
        "test01",
        4242420001,
        BgpTransport(mode=mode, remote_address=remote_address),
    )

    assert info["bgp_local_address"] == expected
    assert info["wireguard_endpoint"] is None
    assert info["public_key"] is None
