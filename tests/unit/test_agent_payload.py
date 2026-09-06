from pathlib import Path

from autopeer.adapters.repository import ConfigRepository, dump_yaml
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
            "own_v4": "172.20.0.1",
            "own_v6": "fd00::1",
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
        "own_v4": "172.20.0.1",
        "own_v6": "fd00::1",
        "mp_bgp": False,
        "ipv4": {"neighbor": "172.20.0.2"},
        "ipv6": {"lla": False, "neighbor": "2602:fc2f::2"},
    }
