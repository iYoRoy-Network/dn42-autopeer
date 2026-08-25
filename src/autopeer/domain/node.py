from __future__ import annotations

from pydantic import BaseModel


class NodeSummary(BaseModel):
    id: str
    name: str
    region: int | None = None
    country: int | None = None
    peering_enabled: bool = False
    deploy_bird_enabled: bool = False
    deploy_wireguard_enabled: bool = False
