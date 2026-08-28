from pathlib import Path

import pytest

from autopeer.adapters.metrics import MetricsConfig, MetricsTarget
from autopeer.adapters.repository import ConfigRepository, dump_yaml
from autopeer.services.metrics_service import MetricsService


class FakeMetricsClient:
    def __init__(self, results: dict[str, list[dict] | Exception]):
        self.results = results

    async def fetch(self, target: MetricsTarget) -> list[dict]:
        result = self.results[target.node]
        if isinstance(result, Exception):
            raise result
        return result


def sample(protocol: str, value: float, name: str = "bird_protocol_up") -> dict:
    return {"name": name, "labels": {"protocol": protocol}, "value": value}


@pytest.mark.asyncio
async def test_online_counts_deduplicate_protocol_samples_and_include_zero():
    config = MetricsConfig(None)
    config.targets = lambda: [
        MetricsTarget(node="online", kind="bird", url="https://online.invalid"),
        MetricsTarget(node="empty", kind="bird", url="https://empty.invalid"),
    ]
    client = FakeMetricsClient(
        {
            "online": [
                sample("dn42_peer_4242420001", 1),
                sample("dn42_peer_4242420001", 1, "bird_bgp_up"),
                sample("dn42_peer_4242420002", 0),
                sample("kernel1", 1),
            ],
            "empty": [],
        }
    )

    counts = await MetricsService(config, client).online_counts_by_node()

    assert counts == {"online": 1, "empty": 0}


@pytest.mark.asyncio
async def test_online_counts_omit_failed_exporter():
    config = MetricsConfig(None)
    config.targets = lambda: [
        MetricsTarget(node="failed", kind="bird", url="https://failed.invalid")
    ]
    client = FakeMetricsClient({"failed": RuntimeError("unavailable")})

    counts = await MetricsService(config, client).online_counts_by_node()

    assert counts == {}


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
