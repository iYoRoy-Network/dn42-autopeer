from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASN_MIN = 1
ASN_MAX = 4_294_967_295
DN42_AUTOPEER_ASN_MIN = 4_242_420_000
DN42_AUTOPEER_ASN_MAX = 4_242_429_999
DESCRIPTION_MAX_LENGTH = 160
ENDPOINT_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class BgpTransportMode(str, Enum):
    ipv6_link_local = "ipv6_link_local"
    ipv4 = "ipv4"
    ipv6 = "ipv6"


def listen_port_for_asn(asn: int) -> int:
    return 20_000 + (asn % 10_000)


def validate_asn(asn: int) -> int:
    if asn < ASN_MIN or asn > ASN_MAX:
        raise ValueError("ASN must be within 1..4294967295")
    return asn


def validate_dn42_autopeer_asn(asn: int) -> int:
    validate_asn(asn)
    if not (DN42_AUTOPEER_ASN_MIN <= asn <= DN42_AUTOPEER_ASN_MAX):
        raise ValueError("MVP autopeer only accepts AS4242420000..AS4242429999")
    return asn


def _reject_control_chars(value: str, field_name: str) -> str:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def validate_base64_key(value: str, field_name: str = "key") -> str:
    _reject_control_chars(value, field_name)
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError(f"{field_name} must be base64") from exc
    if len(raw) != 32:
        raise ValueError(f"{field_name} must decode to 32 bytes")
    return value


def canonical_endpoint(value: str) -> str:
    _reject_control_chars(value, "endpoint")
    if value.startswith("["):
        closing = value.find("]")
        if closing <= 1 or closing + 1 >= len(value) or value[closing + 1] != ":":
            raise ValueError("IPv6 endpoint must be formatted as [addr]:port")
        host = value[1:closing]
        port_text = value[closing + 2 :]
    else:
        if value.count(":") != 1:
            raise ValueError("endpoint must be host:port or [ipv6]:port")
        host, port_text = value.rsplit(":", 1)
    if not host:
        raise ValueError("endpoint host is empty")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("endpoint port must be numeric") from exc
    if not (1 <= port <= 65535):
        raise ValueError("endpoint port must be within 1..65535")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not ENDPOINT_HOST_RE.match(host):
            raise ValueError("endpoint host must be a DNS name, IPv4, or bracketed IPv6 address")
        return f"{host}:{port}"
    if ip.version == 6:
        return f"[{ip.compressed}]:{port}"
    return f"{ip.compressed}:{port}"


def canonical_ip(value: str) -> str:
    _reject_control_chars(value, "ip address")
    return ipaddress.ip_address(value).compressed


def validate_description(value: str | None) -> str | None:
    if value is None:
        return None
    _reject_control_chars(value, "description")
    if len(value) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"description must be at most {DESCRIPTION_MAX_LENGTH} characters")
    return value


class WireGuardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str
    endpoint: str

    @field_validator("public_key")
    @classmethod
    def public_key_valid(cls, value: str) -> str:
        return validate_base64_key(value, "wireguard.public_key")

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value: str) -> str:
        return canonical_endpoint(value)


class WireGuardPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str | None = None
    endpoint: str | None = None

    @field_validator("public_key")
    @classmethod
    def public_key_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_base64_key(value, "wireguard.public_key")

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return canonical_endpoint(value)


class BgpTransport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: BgpTransportMode = BgpTransportMode.ipv6_link_local
    remote_address: str

    @model_validator(mode="after")
    def remote_address_matches_mode(self) -> BgpTransport:
        ip = ipaddress.ip_address(self.remote_address)
        if self.mode == BgpTransportMode.ipv6_link_local:
            if ip.version != 6 or not ip.is_link_local:
                raise ValueError("ipv6_link_local transport requires a fe80::/10 address")
        elif self.mode == BgpTransportMode.ipv4:
            if ip.version != 4:
                raise ValueError("ipv4 transport requires an IPv4 remote address")
        elif self.mode == BgpTransportMode.ipv6 and ip.version != 6:
            raise ValueError("ipv6 transport requires an IPv6 remote address")
        self.remote_address = ip.compressed
        return self


class BgpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: BgpTransport
    address_families: list[Literal["ipv4", "ipv6"]] = Field(
        default_factory=lambda: ["ipv4", "ipv6"]
    )
    extended_next_hop: bool = True

    @field_validator("address_families")
    @classmethod
    def address_families_valid(cls, value: list[str]) -> list[str]:
        normalized = sorted(set(value))
        if not normalized:
            raise ValueError("at least one address family is required")
        # Current BIRD template enables both channels; fail closed for MVP.
        if normalized != ["ipv4", "ipv6"]:
            raise ValueError("current Ansible template supports only ipv4+ipv6 together")
        return normalized


class BgpPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: BgpTransport | None = None
    address_families: list[Literal["ipv4", "ipv6"]] | None = None
    extended_next_hop: bool | None = None

    @field_validator("address_families")
    @classmethod
    def address_families_valid(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return BgpCreate.address_families_valid(value)


class PeerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    wireguard: WireGuardCreate
    bgp: BgpCreate

    @field_validator("description")
    @classmethod
    def description_valid(cls, value: str | None) -> str | None:
        return validate_description(value)


class PeerPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    wireguard: WireGuardPatch | None = None
    bgp: BgpPatch | None = None

    @field_validator("description")
    @classmethod
    def description_valid(cls, value: str | None) -> str | None:
        return validate_description(value)


class PeerResponse(BaseModel):
    node: str
    asn: int
    description: str | None = None
    wireguard_public_key: str
    wireguard_endpoint: str | None = None
    listen_port: int
    bgp_transport: BgpTransport
    address_families: list[Literal["ipv4", "ipv6"]]
    extended_next_hop: bool
    managed_schema: str = "dn42-wireguard-v1"


class PeerStatus(BaseModel):
    node: str
    asn: int
    interface: str
    protocol: str
    wireguard: dict[str, object] = Field(default_factory=dict)
    bgp: dict[str, object] = Field(default_factory=dict)
    node_metrics: dict[str, object] = Field(default_factory=dict)
