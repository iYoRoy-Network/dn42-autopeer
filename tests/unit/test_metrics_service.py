from pathlib import Path

import pytest

from autopeer.adapters.metrics import MetricsConfig, MetricsTarget
from autopeer.adapters.repository import ConfigRepository, dump_yaml
from autopeer.services.metrics_service import MetricsService


class FakeMetricsClient:
    def __init__(self, results: dict[tuple[str, str], list[dict] | Exception]):
        self.results = results
        self.calls: list[tuple[str, str]] = []

    async def fetch(self, target: MetricsTarget) -> list[dict]:
        key = (target.node, target.kind)
        self.calls.append(key)
        result = self.results[key]
        if isinstance(result, Exception):
            raise result
        return result


def sample(protocol: str, value: float, name: str = "bird_protocol_up") -> dict:
    return {"name": name, "labels": {"name": protocol}, "value": value}


@pytest.mark.asyncio
async def test_online_counts_deduplicate_protocol_samples_and_include_zero():
    config = MetricsConfig(None)
    config.targets = lambda: [
        MetricsTarget(node="online", kind="bird", url="https://online.invalid"),
        MetricsTarget(node="empty", kind="bird", url="https://empty.invalid"),
    ]
    client = FakeMetricsClient(
        {
            ("online", "bird"): [
                sample("dn42_peer_4242420001", 1),
                sample("dn42_peer_4242420001", 1, "bird_bgp_up"),
                sample("dn42_peer_4242420002", 0),
                sample("kernel1", 1),
            ],
            ("empty", "bird"): [],
        }
    )
    service = MetricsService(config, client)

    await service.refresh_once()

    assert service.online_counts_by_node() == {"online": 1, "empty": 0}


@pytest.mark.asyncio
async def test_online_counts_omit_failed_exporter():
    config = MetricsConfig(None)
    config.targets = lambda: [
        MetricsTarget(node="failed", kind="bird", url="https://failed.invalid")
    ]
    client = FakeMetricsClient({("failed", "bird"): RuntimeError("unavailable")})
    service = MetricsService(config, client)

    await service.refresh_once()

    assert service.online_counts_by_node() == {}


@pytest.mark.asyncio
async def test_status_uses_bird_and_wireguard_cache():
    config = MetricsConfig(None)
    config.targets = lambda: [
        MetricsTarget(node="node01", kind="bird", url="https://bird.invalid"),
        MetricsTarget(node="node01", kind="wireguard", url="https://wireguard.invalid"),
    ]
    client = FakeMetricsClient(
        {
            ("node01", "bird"): [
                sample("dn42_peer_4242423128", 1),
                sample("dn42_peer_4242423128", 11, "bird_protocol_prefix_import_count"),
                sample("dn42_peer_4242423128", 7, "bird_protocol_prefix_export_count"),
            ],
            ("node01", "wireguard"): [
                {
                    "name": "wireguard_bytes_total",
                    "labels": {"interface": "dn42_4242423128", "direction": "rx"},
                    "value": 100,
                },
                {
                    "name": "wireguard_bytes_total",
                    "labels": {"interface": "dn42_4242423128", "direction": "tx"},
                    "value": 200,
                },
                {
                    "name": "wireguard_duration_since_latest_handshake",
                    "labels": {"interface": "dn42_4242423128"},
                    "value": 9000,
                },
            ],
        }
    )
    service = MetricsService(config, client)

    await service.refresh_once()
    statuses = service.status_for_asn(4242423128)

    assert statuses[0].bgp == {"up": True, "routes_imported": 11.0, "routes_exported": 7.0}
    assert statuses[0].wireguard["rx_bytes"] == 100
    assert statuses[0].wireguard["tx_bytes"] == 200
    assert statuses[0].wireguard["latest_handshake_age_seconds"] == 9


@pytest.mark.asyncio
async def test_node_cache_exposes_totals():
    config = MetricsConfig(None)
    config.targets = lambda: [MetricsTarget(node="node01", kind="node", url="https://node.invalid")]
    client = FakeMetricsClient(
        {
            ("node01", "node"): [
                {
                    "name": "node_network_receive_bytes_total",
                    "labels": {"device": "dn42_1"},
                    "value": 100,
                },
                {
                    "name": "node_network_transmit_bytes_total",
                    "labels": {"device": "dn42_1"},
                    "value": 200,
                },
                {
                    "name": "node_network_receive_bytes_total",
                    "labels": {"device": "eth0"},
                    "value": 1000,
                },
            ]
        }
    )
    service = MetricsService(config, client)

    await service.refresh_once()

    runtime = service.node_metrics_by_node()["node01"]
    assert runtime.rx_bytes == 1100
    assert runtime.tx_bytes == 200


def test_metrics_config_reads_repository_exporters(tmp_path: Path):
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
                    "exporters": {
                        "bird": "https://bird.example/metrics",
                        "wireguard": None,
                    }
                },
            }
        },
    )

    targets = MetricsConfig(None, ConfigRepository(tmp_path)).targets()

    assert targets == [
        MetricsTarget(
            node="test01",
            kind="bird",
            url="https://bird.example/metrics",
        )
    ]
