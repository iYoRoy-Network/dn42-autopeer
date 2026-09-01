from pathlib import Path

from autopeer.adapters.repository import ConfigRepository, dump_yaml


def test_repository_reads_nodes_and_peers_from_snapshot(tmp_path: Path):
    dump_yaml(
        tmp_path / "ansible" / "inventory.yml",
        {"bird_nodes": {"hosts": {"test01": None}}},
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "main.yml",
        {"node": {"name": "Test 01", "peering": {"enabled": True}}},
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "bird-dn42.yml",
        {"dn42": {"own_ip": "172.20.0.1", "own_ipv6": "fd00::1"}},
    )
    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "dn42-peers" / "4242420001.yml",
        {"asn": 4242420001, "wireguard": {"listen_port": 20001}},
    )

    repo = ConfigRepository(tmp_path)
    repo.refresh_snapshot()

    assert repo.list_nodes()[0].peer_count == 1
    assert repo.list_peer_asns("test01") == [4242420001]

    dump_yaml(
        tmp_path / "ansible" / "host_vars" / "test01" / "dn42-peers" / "4242420002.yml",
        {"asn": 4242420002, "wireguard": {"listen_port": 20002}},
    )

    assert repo.list_peer_asns("test01") == [4242420001]

    repo.refresh_snapshot()

    assert repo.list_peer_asns("test01") == [4242420001, 4242420002]
