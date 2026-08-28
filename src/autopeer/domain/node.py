from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

NODE_ENDPOINT_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


class NodeListenPortRange(BaseModel):
    min: int | None = Field(default=None, ge=1, le=65535)
    max: int | None = Field(default=None, ge=1, le=65535)


class NodeListenPortPolicy(BaseModel):
    mode: Literal["asn_suffix", "range"] = "asn_suffix"
    port_min: int | None = Field(default=None, ge=1, le=65535)
    port_max: int | None = Field(default=None, ge=1, le=65535)
    range: NodeListenPortRange | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "NodeListenPortPolicy":
        if self.range is not None:
            if self.port_min is None:
                self.port_min = self.range.min
            if self.port_max is None:
                self.port_max = self.range.max
        if self.mode == "range":
            if self.port_min is None or self.port_max is None:
                raise ValueError("range listen-port mode requires min and max")
            if self.port_min > self.port_max:
                raise ValueError("listen-port range min must not exceed max")
        return self


class NodePeeringMetadata(BaseModel):
    endpoint: str | None = None
    publickey: str | None = None
    listen_port_policy: NodeListenPortPolicy = Field(default_factory=NodeListenPortPolicy)
    exporters: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, value: object) -> "NodePeeringMetadata":
        if not isinstance(value, dict):
            return cls()
        endpoint = value.get("endpoint")
        if endpoint in ("", None):
            endpoint = None
        elif not isinstance(endpoint, str) or not NODE_ENDPOINT_RE.fullmatch(endpoint):
            raise ValueError("node.peering.endpoint must be a DNS name without a port")
        public_key = value.get("publickey", value.get("public_key"))
        if public_key in ("", None):
            public_key = None
        return cls(
            endpoint=endpoint,
            publickey=public_key,
            listen_port_policy=value.get("listen_port_policy") or {},
            exporters={
                str(kind): str(url)
                for kind, url in (value.get("exporters") or {}).items()
                if url is not None and url != ""
            },
        )


class NodeSummary(BaseModel):
    id: str
    name: str
    peering_enabled: bool = False
    peer_count: int = 0
    online_peer_count: int | None = None
    peering: NodePeeringMetadata = Field(default_factory=NodePeeringMetadata)
