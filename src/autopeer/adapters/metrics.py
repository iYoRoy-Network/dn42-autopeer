from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import yaml
from prometheus_client.parser import text_string_to_metric_families

if TYPE_CHECKING:
    from autopeer.adapters.repository import ConfigRepository


@dataclass(frozen=True)
class MetricsTarget:
    node: str
    kind: str
    url: str


class MetricsConfig:
    def __init__(self, path: Path | None, repository: "ConfigRepository" | None = None):
        self.path = path
        self.repository = repository

    def targets(self) -> list[MetricsTarget]:
        data = {}
        if self.path is not None and self.path.exists():
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if self.repository is not None:
            for node in self.repository.list_nodes():
                if node.peering.exporters:
                    data.setdefault("nodes", {}).setdefault(node.id, {}).update(
                        node.peering.exporters
                    )
        result: list[MetricsTarget] = []
        for node, mapping in (data.get("nodes") or {}).items():
            if isinstance(mapping, str):
                result.append(MetricsTarget(node=node, kind="default", url=mapping))
                continue
            for kind, url in (mapping or {}).items():
                if url:
                    result.append(MetricsTarget(node=node, kind=kind, url=str(url)))
        return result


class MetricsClient:
    def __init__(self, timeout: float):
        self.timeout = timeout

    async def fetch(self, target: MetricsTarget) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(target.url)
            response.raise_for_status()
        samples: list[dict[str, Any]] = []
        for family in text_string_to_metric_families(response.text):
            for sample in family.samples:
                name, labels, value = sample.name, sample.labels, sample.value
                samples.append({"name": name, "labels": dict(labels), "value": float(value)})
        return samples
