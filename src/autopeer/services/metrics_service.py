from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from autopeer.adapters.metrics import MetricsClient, MetricsConfig
from autopeer.domain.peer import PeerStatus


class MetricsService:
    def __init__(self, config: MetricsConfig, client: MetricsClient):
        self.config = config
        self.client = client

    async def online_counts_by_node(self) -> dict[str, int]:
        targets = [target for target in self.config.targets() if target.kind == "bird"]
        fetched = await asyncio.gather(
            *(self.client.fetch(target) for target in targets),
            return_exceptions=True,
        )
        counts: dict[str, int] = {}
        for target, result in zip(targets, fetched, strict=False):
            if isinstance(result, Exception):
                continue
            protocols: set[str] = set()
            for sample in result:
                labels = sample.get("labels", {})
                protocol = labels.get("protocol") or labels.get("name") or ""
                if not str(protocol).startswith("dn42_peer_"):
                    continue
                metric_name = sample.get("name", "")
                if (metric_name.endswith("_up") or metric_name == "bird_protocol_up") and bool(
                    sample.get("value")
                ):
                    protocols.add(str(protocol))
            counts[target.node] = counts.get(target.node, 0) + len(protocols)
        return counts

    async def status_for_asn(self, asn: int) -> list[PeerStatus]:
        targets = self.config.targets()
        fetched = await asyncio.gather(
            *(self.client.fetch(target) for target in targets),
            return_exceptions=True,
        )
        by_node_kind: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for target, result in zip(targets, fetched, strict=False):
            if isinstance(result, Exception):
                by_node_kind[(target.node, target.kind)] = [{"error": str(result)}]
            else:
                by_node_kind[(target.node, target.kind)] = result

        nodes = sorted({target.node for target in targets})
        statuses: list[PeerStatus] = []
        for node in nodes:
            interface = f"dn42_{asn}"
            protocol = f"dn42_peer_{asn}"
            statuses.append(
                PeerStatus(
                    node=node,
                    asn=asn,
                    interface=interface,
                    protocol=protocol,
                    wireguard=self._wireguard_summary(
                        by_node_kind.get((node, "wireguard"), []), interface
                    ),
                    bgp=self._bird_summary(by_node_kind.get((node, "bird"), []), protocol),
                    node_metrics=self._node_summary(
                        by_node_kind.get((node, "node"), []), interface
                    ),
                )
            )
        return statuses

    def _wireguard_summary(self, samples: list[dict[str, Any]], interface: str) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for sample in samples:
            labels = sample.get("labels", {})
            if labels.get("interface") != interface and labels.get("device") != interface:
                continue
            name = sample.get("name")
            if "receive_bytes" in name or "rx_bytes" in name:
                summary["rx_bytes"] = sample.get("value")
            elif "transmit_bytes" in name or "tx_bytes" in name:
                summary["tx_bytes"] = sample.get("value")
            elif "handshake" in name:
                summary["latest_handshake_seconds"] = sample.get("value")
        summary["present"] = bool(summary)
        return summary

    def _bird_summary(self, samples: list[dict[str, Any]], protocol: str) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for sample in samples:
            labels = sample.get("labels", {})
            if labels.get("protocol") != protocol and labels.get("name") != protocol:
                continue
            metric_name = sample.get("name")
            if metric_name.endswith("_up") or metric_name == "bird_protocol_up":
                summary["up"] = bool(sample.get("value"))
            elif "import" in metric_name and "route" in metric_name:
                summary["routes_imported"] = sample.get("value")
            elif "export" in metric_name and "route" in metric_name:
                summary["routes_exported"] = sample.get("value")
        return summary

    def _node_summary(self, samples: list[dict[str, Any]], interface: str) -> dict[str, Any]:
        by_direction: dict[str, float] = defaultdict(float)
        for sample in samples:
            labels = sample.get("labels", {})
            if labels.get("device") != interface:
                continue
            name = sample.get("name")
            if name == "node_network_receive_bytes_total":
                by_direction["rx_bytes"] = sample.get("value", 0.0)
            elif name == "node_network_transmit_bytes_total":
                by_direction["tx_bytes"] = sample.get("value", 0.0)
        return dict(by_direction)
