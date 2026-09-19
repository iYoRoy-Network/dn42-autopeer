from pathlib import Path

import pytest

from autopeer.adapters.repository import ConfigRepository, dump_yaml, load_yaml
from autopeer.domain.peer import BgpCreate


def seeded_repo(tmp_path: Path) -> ConfigRepository:
    dump_yaml(
        tmp_path / "ansible" / "inventory.yml",
        {"bird_nodes": {"hosts": {"test01": None}}},
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "main.yml",
        {
            "node": {
                "name": "test01",
                "peering": {
                    "enabled": True,
                    "agent_url": "https://agent.test01.invalid",
                },
            }
        },
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "bird-dn42.yml",
        {"dn42": {"own_ip": "172.20.0.1", "own_ipv6": "fd00::1"}},
    )
    repo = ConfigRepository(tmp_path)
    repo.refresh_snapshot()
    return repo


def test_agent_payload_for_mp_bgp(tmp_path: Path):
    repo = seeded_repo(tmp_path)
    peer = repo.build_peer_yaml(
        node="test01",
        asn=4242422001,
        description="contact",
        public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        endpoint="peer.example:22024",
        bgp=BgpCreate.model_validate(
            {
                "mp_bgp": True,
                "ipv4_enabled": False,
                "ipv6_enabled": True,
                "ipv6_mode": "link_local",
                "ipv6_link_local_address": "fe80::1",
            }
        ),
        listen_port=22001,
        mtu=1420,
    )

    payload = repo.agent_peer_payload("test01", 4242422001, peer)

    assert payload == {
        "wireguard": {
            "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "endpoint": "peer.example:22024",
            "listen_port": 22001,
            "mtu": 1420,
        },
        "bgp": {
            "mp_bgp": True,
            "ipv6": {"lla": True, "neighbor": "fe80::1"},
        },
    }


def test_agent_payload_for_dual_independent_sessions(tmp_path: Path):
    repo = seeded_repo(tmp_path)
    peer = repo.build_peer_yaml(
        node="test01",
        asn=4242422002,
        description="contact",
        public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        endpoint="peer.example:22025",
        bgp=BgpCreate.model_validate(
            {
                "mp_bgp": False,
                "ipv4_enabled": True,
                "ipv6_enabled": True,
                "ipv4_address": "172.20.0.2",
                "ipv6_mode": "global",
                "ipv6_address": "2602:fc2f::2",
            }
        ),
        listen_port=22002,
        mtu=1410,
    )

    payload = repo.agent_peer_payload("test01", 4242422002, peer)

    assert payload["bgp"] == {
        "mp_bgp": False,
        "ipv4": {"neighbor": "172.20.0.2"},
        "ipv6": {"lla": False, "neighbor": "2602:fc2f::2"},
    }


@pytest.mark.parametrize(
    "bgp",
    [
        pytest.param(
            {"mp_bgp": True, "ipv6_mode": "link_local", "ipv6_link_local_address": "fe80::1"}
        ),
        pytest.param({"mp_bgp": True, "ipv6_mode": "global", "ipv6_address": "2602:fc2f::2"}),
        pytest.param({"ipv4_enabled": True, "ipv6_enabled": False, "ipv4_address": "172.20.0.2"}),
        pytest.param(
            {
                "ipv4_enabled": True,
                "ipv6_enabled": True,
                "ipv4_address": "172.20.0.2",
                "ipv6_mode": "global",
                "ipv6_address": "2602:fc2f::2",
            }
        ),
    ],
    ids=["mp-bgp-link-local", "mp-bgp-global", "ipv4-only", "dual-independent"],
)
def test_build_peer_yaml_is_serializable(tmp_path: Path, bgp: dict):
    """The generated peer document must survive a YAML round trip.

    BgpTransportMode is a str-Enum, so Pydantic dumps it as a plain string but a
    raw enum placed into the document is not representable by yaml.safe_dump.
    Building the document without writing it hid that from the other tests.
    """
    repo = seeded_repo(tmp_path)

    peer = repo.build_peer_yaml(
        node="test01",
        asn=4242422003,
        description="contact",
        public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        endpoint="peer.example:22026",
        bgp=BgpCreate.model_validate(bgp),
        listen_port=22003,
        mtu=1420,
    )

    path = repo.write_peer("test01", 4242422003, peer)

    assert load_yaml(path) == peer
    for session in peer["bgp"]["sessions"]:
        assert isinstance(session["transport"], str)
