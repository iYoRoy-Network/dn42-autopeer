from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from time import time
from typing import Any

from autopeer.adapters.metrics import MetricsClient, MetricsConfig, MetricsTarget
from autopeer.domain.node import NodeRuntimeMetrics
from autopeer.domain.peer import PeerStatus


@dataclass(frozen=True)
class MetricsSnapshot:
    samples: list[dict[str, Any]]
    collected_at: float
    error: str | None = None


class MetricsService:
    """Collect exporter data in the background and serve API reads from memory."""

    def __init__(
        self,
        config: MetricsConfig,
        client: MetricsClient,
        *,
        refresh_seconds: float = 30.0,
        max_concurrency: int = 4,
    ):
        self.config = config
        self.client = client
        self.refresh_seconds = refresh_seconds
        self.max_concurrency = max_concurrency
        self._snapshots: dict[tuple[str, str], MetricsSnapshot] = {}
        self._node_metrics: dict[str, NodeRuntimeMetrics] = {}
        self._task: asyncio.Task[None] | None = None
        self._refresh_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._refresh_loop(), name="autopeer-metrics-collector"
            )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _refresh_loop(self) -> None:
        while True:
            await self.refresh_once()
            await asyncio.sleep(self.refresh_seconds)

    async def refresh_once(self) -> None:
        """Fetch every configured exporter once, bounded by a shared semaphore."""
        if self._refresh_lock.locked():
            return
        async with self._refresh_lock:
            targets = self.config.targets()
            active_keys = {(target.node, target.kind) for target in targets}
            self._snapshots = {
                key: snapshot for key, snapshot in self._snapshots.items() if key in active_keys
            }
            semaphore = asyncio.Semaphore(self.max_concurrency)
            await asyncio.gather(
                *(self._refresh_target(target, semaphore) for target in targets),
                return_exceptions=True,
            )

    async def _refresh_target(
        self,
        target: MetricsTarget,
        semaphore: asyncio.Semaphore,
    ) -> None:
        key = (target.node, target.kind)
        try:
            async with semaphore:
                samples = await self.client.fetch(target)
        except Exception as exc:  # Exporters are optional runtime dependencies.
            previous = self._snapshots.get(key)
            self._snapshots[key] = MetricsSnapshot(
                samples=previous.samples if previous else [],
                collected_at=previous.collected_at if previous else 0.0,
                error=str(exc),
            )
            return

        collected_at = time()
        self._snapshots[key] = MetricsSnapshot(samples=samples, collected_at=collected_at)
        if target.kind == "node":
            self._update_node_metrics(target.node, samples, collected_at)

    def online_counts_by_node(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for (node, kind), snapshot in self._snapshots.items():
            if kind != "bird" or snapshot.error is not None:
                continue
            protocols = {
                self._peer_protocol(self._sample_protocol(sample))
                for sample in snapshot.samples
                if self._sample_protocol(sample).startswith("dn42_peer_")
                and self._is_up_sample(sample)
                and bool(sample.get("value"))
            }
            counts[node] = len(protocols)
        return counts

    def node_metrics_by_node(self) -> dict[str, NodeRuntimeMetrics]:
        return dict(self._node_metrics)

    def status_for_asn(self, asn: int) -> list[PeerStatus]:
        nodes = sorted({node for node, _ in self._snapshots})
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
                        self._samples_for(node, "wireguard"), interface
                    ),
                    bgp=self._bird_summary(self._samples_for(node, "bird"), protocol),
                    node_metrics=self._node_summary(self._samples_for(node, "node"), interface),
                )
            )
        return statuses

    def _samples_for(self, node: str, kind: str) -> list[dict[str, Any]]:
        snapshot = self._snapshots.get((node, kind))
        if snapshot is None or snapshot.error is not None:
            return []
        return snapshot.samples

    @staticmethod
    def _sample_protocol(sample: dict[str, Any]) -> str:
        labels = sample.get("labels", {})
        return str(labels.get("protocol") or labels.get("name") or "")

    @staticmethod
    def _peer_protocol(protocol: str) -> str:
        for suffix in ("_ipv4", "_ipv6"):
            if protocol.endswith(suffix):
                return protocol[: -len(suffix)]
        return protocol

    @staticmethod
    def _is_up_sample(sample: dict[str, Any]) -> bool:
        metric_name = str(sample.get("name", ""))
        return metric_name.endswith("_up") or metric_name == "bird_protocol_up"

    def _wireguard_summary(self, samples: list[dict[str, Any]], interface: str) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for sample in samples:
            labels = sample.get("labels", {})
            if labels.get("interface") != interface and labels.get("device") != interface:
                continue
            name = str(sample.get("name", ""))
            value = sample.get("value")
            if name == "wireguard_bytes_total":
                direction = labels.get("direction")
                if direction == "rx":
                    summary["rx_bytes"] = value
                elif direction == "tx":
                    summary["tx_bytes"] = value
            elif "receive_bytes" in name or "rx_bytes" in name:
                summary["rx_bytes"] = value
            elif "transmit_bytes" in name or "tx_bytes" in name:
                summary["tx_bytes"] = value
            elif "handshake" in name:
                if "duration_since_latest_handshake" in name:
                    summary["latest_handshake_age_seconds"] = float(value or 0) / 1000
                elif value is not None and float(value) >= 946_684_800:
                    summary["latest_handshake_seconds"] = value
                else:
                    summary["latest_handshake_age_seconds"] = value
        summary["present"] = bool(summary)
        return summary

    def _bird_summary(self, samples: list[dict[str, Any]], protocol: str) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        imported_routes = 0.0
        exported_routes = 0.0
        has_imported_routes = False
        has_exported_routes = False
        for sample in samples:
            if self._sample_protocol(sample) != protocol:
                continue
            metric_name = str(sample.get("name", ""))
            value = float(sample.get("value", 0.0))
            if self._is_up_sample(sample):
                summary["up"] = bool(summary.get("up")) or bool(value)
            elif "prefix_import_count" in metric_name or metric_name.endswith("_prefix_import"):
                imported_routes += value
                has_imported_routes = True
            elif "prefix_export_count" in metric_name or metric_name.endswith("_prefix_export"):
                exported_routes += value
                has_exported_routes = True
        if has_imported_routes:
            summary["routes_imported"] = imported_routes
        if has_exported_routes:
            summary["routes_exported"] = exported_routes
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

    def _update_node_metrics(
        self,
        node: str,
        samples: list[dict[str, Any]],
        collected_at: float,
    ) -> None:
        totals = self._node_summary_all_interfaces(samples)
        previous = self._node_metrics.get(node)
        rx_rate: float | None = None
        tx_rate: float | None = None
        if previous is not None and previous.collected_at is not None:
            elapsed = collected_at - previous.collected_at
            if elapsed > 0:
                rx_rate = max(0.0, totals["rx_bytes"] - (previous.rx_bytes or 0.0)) / elapsed
                tx_rate = max(0.0, totals["tx_bytes"] - (previous.tx_bytes or 0.0)) / elapsed
        self._node_metrics[node] = NodeRuntimeMetrics(
            rx_bytes=totals["rx_bytes"],
            tx_bytes=totals["tx_bytes"],
            rx_bytes_per_second=rx_rate,
            tx_bytes_per_second=tx_rate,
            collected_at=collected_at,
        )

    @staticmethod
    def _node_summary_all_interfaces(samples: list[dict[str, Any]]) -> dict[str, float]:
        totals = {"rx_bytes": 0.0, "tx_bytes": 0.0}
        for sample in samples:
            device = str(sample.get("labels", {}).get("device", ""))
            if device == "lo":
                continue
            if sample.get("name") == "node_network_receive_bytes_total":
                totals["rx_bytes"] += float(sample.get("value", 0.0))
            elif sample.get("name") == "node_network_transmit_bytes_total":
                totals["tx_bytes"] += float(sample.get("value", 0.0))
        return totals
