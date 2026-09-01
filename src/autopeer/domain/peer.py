from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The public API accepts only the DN42 private ASN block for self-service peers.
# Broader ASN values are still validated because admins and imported YAML may reference them.
ASN_MIN = 1
ASN_MAX = 4_294_967_295
DN42_AUTOPEER_ASN_MIN = 4_242_420_001
DN42_AUTOPEER_ASN_MAX = 4_242_423_999
DESCRIPTION_MAX_LENGTH = 160
ENDPOINT_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ListenPortMode(str, Enum):
    asn_suffix = "asn_suffix"
    range = "range"


def listen_port_for_asn(asn: int) -> int:
    """Use the last five ASN digits as the default DN42 port."""
    return asn % 100_000


def validate_listen_port(port: int) -> int:
    if not 1 <= port <= 65_535:
        raise ValueError("listen port must be within 1..65535")
    return port


def allocate_listen_port(
    asn: int,
    *,
    mode: ListenPortMode = ListenPortMode.asn_suffix,
    port_min: int | None = None,
    port_max: int | None = None,
    used_ports: set[int] | None = None,
) -> int:
    """Select a stable ASN port or the first free port in a configured pool."""
    if mode == ListenPortMode.asn_suffix:
        return validate_listen_port(listen_port_for_asn(asn))
    if port_min is None or port_max is None:
        raise ValueError("range listen-port mode requires min and max")
    validate_listen_port(port_min)
    validate_listen_port(port_max)
    if port_min > port_max:
        raise ValueError("listen-port range min must not exceed max")
    occupied = used_ports or set()
    for port in range(port_min, port_max + 1):
        if port not in occupied:
            return port
    raise ValueError(f"no free listen port in range {port_min}-{port_max}")


class BgpTransportMode(str, Enum):
    ipv6_link_local = "ipv6_link_local"
    ipv4 = "ipv4"
    ipv6 = "ipv6"


class BgpSessionMode(str, Enum):
    mp_bgp_ipv6_link_local = "mp_bgp_ipv6_link_local"
    mp_bgp_ipv6_global = "mp_bgp_ipv6_global"
    dual_ipv6_link_local = "dual_ipv6_link_local"
    dual_ipv6_global = "dual_ipv6_global"
    ipv4 = "ipv4"
    ipv6 = "ipv6"


def validate_asn(asn: int) -> int:
    if asn < ASN_MIN or asn > ASN_MAX:
        raise ValueError("ASN must be within 1..4294967295")
    return asn


def validate_dn42_autopeer_asn(asn: int) -> int:
    validate_asn(asn)
    if not (DN42_AUTOPEER_ASN_MIN <= asn <= DN42_AUTOPEER_ASN_MAX):
        raise ValueError("MVP autopeer only accepts AS4242420001..AS4242423999")
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
    mtu: int = Field(default=1420, ge=576, le=9000)

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
    mtu: int | None = Field(default=None, ge=576, le=9000)

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

    mp_bgp: bool = False
    ipv4_enabled: bool = True
    ipv6_enabled: bool = True
    ipv6_mode: Literal["link_local", "global"] = "link_local"
    ipv4_address: str | None = None
    ipv6_address: str | None = None
    ipv6_link_local_address: str | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_fields(cls, value):
        if isinstance(value, dict) and "transport" in value:
            transport = value["transport"]
            mode = transport.get("mode")
            converted = dict(value)
            converted.pop("transport", None)
            families = converted.pop("address_families", ["ipv4", "ipv6"])
            converted["ipv4_enabled"] = "ipv4" in families
            converted["ipv6_enabled"] = "ipv6" in families
            if mode == "ipv4":
                converted["ipv4_address"] = transport.get("remote_address")
                converted["ipv6_enabled"] = False
            elif mode == "ipv6":
                converted["ipv6_address"] = transport.get("remote_address")
                converted["ipv4_enabled"] = False
                converted["ipv6_mode"] = "global"
            else:
                converted["ipv6_link_local_address"] = transport.get("remote_address")
                converted["ipv6_mode"] = "link_local"
            converted["mp_bgp"] = False
            if mode == "ipv6_link_local":
                converted["ipv4_enabled"] = False
            converted.pop("extended_next_hop", None)
            return converted
        return value

    @model_validator(mode="after")
    def configuration_valid(self) -> "BgpCreate":
        if self.mp_bgp:
            if not self.ipv6_enabled:
                raise ValueError("MP-BGP requires IPv6 to be enabled")
            self.ipv4_enabled = False
        elif not self.ipv4_enabled and not self.ipv6_enabled:
            raise ValueError("at least one address family must be enabled")
        if self.ipv4_enabled:
            self._validate_address(self.ipv4_address, 4, "ipv4_address")
        if self.ipv6_enabled:
            if self.ipv6_mode == "global":
                self._validate_address(self.ipv6_address, 6, "ipv6_address", require_global=True)
            else:
                self._validate_address(
                    self.ipv6_link_local_address,
                    6,
                    "ipv6_link_local_address",
                    require_link_local=True,
                )
        self.normalized()
        return self

    @staticmethod
    def _validate_address(
        value: str | None,
        version: int,
        field_name: str,
        *,
        require_global: bool = False,
        require_link_local: bool = False,
    ) -> None:
        if not value:
            raise ValueError(f"{field_name} is required")
        address = ipaddress.ip_address(value)
        if address.version != version:
            raise ValueError(f"{field_name} has the wrong address family")
        if require_global and (address.is_link_local or not address.is_global):
            raise ValueError("ipv6_address must be a global unicast address")
        if require_link_local and not address.is_link_local:
            raise ValueError("ipv6_link_local_address must be link-local")

    @property
    def address_families(self) -> list[str]:
        if self.mp_bgp:
            return ["ipv4", "ipv6"]
        return [
            family
            for family, enabled in (("ipv4", self.ipv4_enabled), ("ipv6", self.ipv6_enabled))
            if enabled
        ]

    def normalized(self) -> "BgpCreate":
        for field_name in ("ipv4_address", "ipv6_address", "ipv6_link_local_address"):
            value = getattr(self, field_name)
            if value:
                setattr(self, field_name, ipaddress.ip_address(value).compressed)
        return self


class BgpPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mp_bgp: bool | None = None
    ipv4_enabled: bool | None = None
    ipv6_enabled: bool | None = None
    ipv6_mode: Literal["link_local", "global"] | None = None
    ipv4_address: str | None = None
    ipv6_address: str | None = None
    ipv6_link_local_address: str | None = None

    @field_validator("ipv4_address", "ipv6_address", "ipv6_link_local_address")
    @classmethod
    def address_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ipaddress.ip_address(value).compressed


class PeerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact: str
    wireguard: WireGuardCreate
    bgp: BgpCreate

    @field_validator("contact")
    @classmethod
    def contact_valid(cls, value: str) -> str:
        normalized = validate_description(value.strip())
        if not normalized:
            raise ValueError("contact information is required")
        return normalized


class PeerPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact: str | None = None
    wireguard: WireGuardPatch | None = None
    bgp: BgpPatch | None = None

    @field_validator("contact")
    @classmethod
    def contact_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = validate_description(value.strip())
        if not normalized:
            raise ValueError("contact information must not be empty")
        return normalized


class PeerConnectionInfo(BaseModel):
    wireguard_endpoint: str | None = None
    public_key: str | None = None
    listen_port: int
    bgp_transport: BgpTransportMode
    bgp_local_address: str


class PeerResponse(BaseModel):
    node: str
    asn: int
    description: str | None = None
    wireguard_public_key: str
    wireguard_endpoint: str | None = None
    listen_port: int
    mtu: int
    bgp_transport: BgpTransport
    address_families: list[Literal["ipv4", "ipv6"]]
    extended_next_hop: bool
    session_mode: BgpSessionMode | None = None
    bgp: dict[str, object] = Field(default_factory=dict)
    connection_info: PeerConnectionInfo | None = None
    managed_schema: str = "dn42-wireguard-v1"


class PeerStatus(BaseModel):
    node: str
    asn: int
    interface: str
    protocol: str
    wireguard: dict[str, object] = Field(default_factory=dict)
    bgp: dict[str, object] = Field(default_factory=dict)
    node_metrics: dict[str, object] = Field(default_factory=dict)
