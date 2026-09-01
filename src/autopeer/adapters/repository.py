from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml

from autopeer.domain.node import NodePeeringMetadata, NodeSummary
from autopeer.domain.peer import (
    BgpCreate,
    BgpSessionMode,
    BgpTransport,
    BgpTransportMode,
    ListenPortMode,
    PeerConnectionInfo,
    PeerResponse,
    allocate_listen_port,
    listen_port_for_asn,
)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def dump_yaml(path: Path, data: dict[str, Any], mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


class ConfigRepository:
    """Filesystem adapter for the Bird2-Configuration repository.

    This layer is the only place that understands the Ansible/YAML layout. The
    rest of the backend deals with validated API/domain models instead of raw
    paths, and intentionally reads peer files directly instead of relying on
    ansible-inventory's recursive host_vars merge behavior.
    """

    def __init__(self, root: Path):
        self.root = root
        self.ansible_dir = self.root / "ansible"

    def ensure_exists(self) -> None:
        if not self.ansible_dir.is_dir():
            raise FileNotFoundError(f"not an Ansible config repo: {self.root}")

    def node_dir(self, node: str) -> Path:
        self._validate_node_id(node)
        return self.ansible_dir / "host_vars" / node

    def peer_dir(self, node: str) -> Path:
        return self.node_dir(node) / "dn42-peers"

    def peer_file(self, node: str, asn: int) -> Path:
        return self.peer_dir(node) / f"{asn}.yml"

    def list_inventory_nodes(self) -> list[str]:
        inv = load_yaml(self.ansible_dir / "inventory.yml")
        hosts = ((inv.get("bird_nodes") or {}).get("hosts")) or {}
        return sorted(hosts)

    def list_nodes(self) -> list[NodeSummary]:
        nodes: list[NodeSummary] = []
        for node in self.list_inventory_nodes():
            node_vars = load_yaml(self.node_dir(node) / "main.yml")
            meta = node_vars.get("node") or {}
            peering = meta.get("peering") or {}
            nodes.append(
                NodeSummary(
                    id=node,
                    name=meta.get("name", node),
                    peering_enabled=bool(peering.get("enabled", True)),
                    peer_count=len(self.list_peer_asns(node)),
                    peering=NodePeeringMetadata.from_yaml(peering),
                )
            )
        return nodes

    def node_metadata(self, node: str) -> NodePeeringMetadata:
        self.require_node(node)
        return next(item.peering for item in self.list_nodes() if item.id == node)

    def allocated_listen_port(
        self,
        node: str,
        asn: int,
        existing: dict[str, Any] | None = None,
    ) -> int:
        current = ((existing or {}).get("wireguard") or {}).get("listen_port")
        if current is not None:
            return int(current)
        metadata = self.node_metadata(node)
        policy = metadata.listen_port_policy
        used: set[int] = set()
        for peer_asn in self.list_peer_asns(node):
            peer = self.read_peer(node, peer_asn) or {}
            port = (peer.get("wireguard") or {}).get("listen_port")
            if port is not None:
                used.add(int(port))
        return allocate_listen_port(
            asn,
            mode=ListenPortMode(policy.mode),
            port_min=policy.port_min,
            port_max=policy.port_max,
            used_ports=used,
        )

    def require_node(self, node: str) -> None:
        if node not in set(self.list_inventory_nodes()):
            raise KeyError(node)

    def read_peer(self, node: str, asn: int) -> dict[str, Any] | None:
        path = self.peer_file(node, asn)
        if not path.exists():
            return None
        data = load_yaml(path)
        # The filename is the ownership boundary: AS424242xxxx may only edit
        # dn42-peers/424242xxxx.yml, so the inner YAML must agree with the path.
        if data.get("asn") != asn:
            raise ValueError(f"peer file {path} has mismatched ASN {data.get('asn')}")
        return data

    def list_peer_asns(self, node: str) -> list[int]:
        directory = self.peer_dir(node)
        if not directory.exists():
            return []
        asns: list[int] = []
        for path in sorted(directory.glob("*.yml"), key=lambda item: item.name):
            try:
                asn = int(path.stem)
            except ValueError:
                continue
            data = load_yaml(path)
            if data.get("asn") != asn:
                raise ValueError(f"peer file {path} has mismatched ASN {data.get('asn')}")
            asns.append(asn)
        return sorted(asns)

    def list_peers(self, node: str) -> list[PeerResponse]:
        return [
            self.peer_to_response(node, asn, self.read_peer(node, asn) or {})
            for asn in self.list_peer_asns(node)
        ]

    def write_peer(self, node: str, asn: int, data: dict[str, Any]) -> Path:
        data = dict(data)
        data["asn"] = asn
        path = self.peer_file(node, asn)
        dump_yaml(path, data)
        return path

    def delete_peer(self, node: str, asn: int) -> Path:
        path = self.peer_file(node, asn)
        if path.exists():
            path.unlink()
        return path

    def node_dn42_source(self, node: str, mode: BgpTransportMode) -> str | None:
        dn42 = load_yaml(self.node_dir(node) / "bird-dn42.yml").get("dn42") or {}
        if mode == BgpTransportMode.ipv4:
            return dn42.get("own_ip")
        if mode == BgpTransportMode.ipv6:
            return dn42.get("own_ipv6")
        return None

    def connection_info(
        self,
        node: str,
        asn: int,
        transport: BgpTransport,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = self.node_metadata(node)
        port = self.allocated_listen_port(node, asn, existing)
        if transport.mode == BgpTransportMode.ipv6_link_local:
            local_address = "fe80::2024"
        else:
            local_address = self.node_dn42_source(node, transport.mode)
            if not local_address:
                raise ValueError(f"node {node} has no source address for {transport.mode}")
            local_address = ipaddress.ip_address(local_address).compressed
        endpoint = f"{metadata.endpoint}:{port}" if metadata.endpoint else None
        return {
            "wireguard_endpoint": endpoint,
            "public_key": metadata.publickey,
            "listen_port": port,
            "bgp_transport": transport.mode,
            "bgp_local_address": local_address,
        }

    def _bgp_sessions(self, node: str, asn: int, bgp: BgpCreate) -> list[dict[str, Any]]:
        if bgp.mp_bgp:
            address = (
                bgp.ipv6_link_local_address if bgp.ipv6_mode == "link_local" else bgp.ipv6_address
            )
            transport = (
                BgpTransportMode.ipv6_link_local
                if bgp.ipv6_mode == "link_local"
                else BgpTransportMode.ipv6
            )
            return [
                {
                    "name": "mp-bgp",
                    "transport": transport,
                    "remote_address": address,
                    "interface": f"dn42_{asn}",
                }
            ]
        sessions: list[dict[str, Any]] = []
        if bgp.ipv4_enabled:
            sessions.append(
                {
                    "name": "ipv4",
                    "transport": BgpTransportMode.ipv4,
                    "remote_address": bgp.ipv4_address,
                }
            )
        if bgp.ipv6_enabled:
            transport = (
                BgpTransportMode.ipv6_link_local
                if bgp.ipv6_mode == "link_local"
                else BgpTransportMode.ipv6
            )
            address = (
                bgp.ipv6_link_local_address if bgp.ipv6_mode == "link_local" else bgp.ipv6_address
            )
            sessions.append(
                {
                    "name": "ipv6",
                    "transport": transport,
                    "remote_address": address,
                    "interface": f"dn42_{asn}",
                }
            )
        return sessions

    def build_peer_yaml(
        self,
        *,
        node: str,
        asn: int,
        description: str | None,
        public_key: str,
        endpoint: str,
        bgp: BgpCreate,
        listen_port: int | None = None,
        mtu: int = 1420,
    ) -> dict[str, Any]:
        """Translate the public peer request into explicit BIRD sessions."""
        wireguard: dict[str, Any] = {
            "public_key": public_key,
            "listen_port": listen_port if listen_port is not None else listen_port_for_asn(asn),
            "fwmark": "4242",
            "mtu": mtu,
            "endpoint": endpoint,
        }
        sessions = self._bgp_sessions(node, asn, bgp.normalized())
        serialized_sessions: list[dict[str, Any]] = []
        for session in sessions:
            item = {
                "name": session["name"],
                "address_families": ["ipv4", "ipv6"] if bgp.mp_bgp else [session["name"]],
                "extended_next_hop": bgp.mp_bgp,
                "neighbor": session["remote_address"],
                "transport": session["transport"],
            }
            if session.get("interface"):
                item["interface"] = session["interface"]
            transport = session["transport"]
            if transport != BgpTransportMode.ipv6_link_local:
                source = self.node_dn42_source(node, transport)
                if not source:
                    raise ValueError(f"node {node} has no source address for {transport}")
                item["source"] = ipaddress.ip_address(source).compressed
            serialized_sessions.append(item)
        result: dict[str, Any] = {
            "description": description or f"AS{asn}",
            "asn": asn,
            "wireguard": wireguard,
            "bgp": {
                "mode": "mp_bgp" if bgp.mp_bgp else "independent",
                "sessions": serialized_sessions,
                "extended_next_hop": bgp.mp_bgp,
            },
        }
        # Keep the legacy top-level transport fields for WireGuard route hooks
        # and older renderers while the BIRD source uses explicit sessions.
        for session in serialized_sessions:
            if session["transport"] == BgpTransportMode.ipv6_link_local:
                result["lla"] = session["neighbor"]
            elif "dst" not in result:
                result["dst"] = session["neighbor"]
                result["src"] = session["source"]
        return result

    def peer_to_response(self, node: str, asn: int, data: dict[str, Any]) -> PeerResponse:
        wg = data.get("wireguard") or {}
        bgp = data.get("bgp") or {}
        raw_sessions = bgp.get("sessions") or []
        if raw_sessions:
            first = raw_sessions[0]
            transport_mode = BgpTransportMode(first.get("transport", "ipv6_link_local"))
            remote_address = first.get("neighbor", "fe80::")
            if bgp.get("mode") == "mp_bgp":
                session_mode = (
                    BgpSessionMode.mp_bgp_ipv6_link_local
                    if transport_mode == BgpTransportMode.ipv6_link_local
                    else BgpSessionMode.mp_bgp_ipv6_global
                )
            elif len(raw_sessions) == 2:
                session_mode = (
                    BgpSessionMode.dual_ipv6_link_local
                    if transport_mode == BgpTransportMode.ipv6_link_local
                    else BgpSessionMode.dual_ipv6_global
                )
            else:
                session_mode = (
                    BgpSessionMode.ipv4
                    if transport_mode == BgpTransportMode.ipv4
                    else BgpSessionMode.ipv6
                )
            families = raw_sessions[0].get("address_families", ["ipv4", "ipv6"])
        elif data.get("lla"):
            transport_mode = BgpTransportMode.ipv6_link_local
            remote_address = data["lla"]
            session_mode = (
                BgpSessionMode.mp_bgp_ipv6_link_local
                if bgp.get("extended_next_hop")
                else BgpSessionMode.ipv6
            )
            families = ["ipv4", "ipv6"] if bgp.get("extended_next_hop") else ["ipv6"]
        elif data.get("dst"):
            remote_address = data["dst"]
            transport_mode = (
                BgpTransportMode.ipv4
                if ipaddress.ip_address(remote_address).version == 4
                else BgpTransportMode.ipv6
            )
            session_mode = (
                BgpSessionMode.ipv4
                if transport_mode == BgpTransportMode.ipv4
                else BgpSessionMode.ipv6
            )
            families = ["ipv4"] if transport_mode == BgpTransportMode.ipv4 else ["ipv6"]
        else:
            transport_mode = BgpTransportMode.ipv6_link_local
            remote_address = "fe80::"
            session_mode = BgpSessionMode.ipv6
            families = ["ipv6"]
        transport = BgpTransport(mode=transport_mode, remote_address=remote_address)
        response_bgp = dict(bgp)
        response_bgp["mp_bgp"] = bool(bgp.get("mode") == "mp_bgp")
        response_bgp["ipv4_enabled"] = response_bgp["mp_bgp"] or "ipv4" in families
        response_bgp["ipv6_enabled"] = "ipv6" in families
        for session in raw_sessions:
            if session.get("name") == "ipv4":
                response_bgp["ipv4_address"] = session.get("neighbor")
            elif session.get("name") in {"ipv6", "mp-bgp"}:
                if session.get("transport") == BgpTransportMode.ipv6_link_local.value:
                    response_bgp["ipv6_mode"] = "link_local"
                    response_bgp["ipv6_link_local_address"] = session.get("neighbor")
                    response_bgp["ipv6_link_local_interface"] = session.get("interface")
                else:
                    response_bgp["ipv6_mode"] = "global"
                    response_bgp["ipv6_address"] = session.get("neighbor")
        return PeerResponse(
            node=node,
            asn=asn,
            description=data.get("description"),
            wireguard_public_key=wg.get("public_key", ""),
            wireguard_endpoint=wg.get("endpoint"),
            listen_port=int(wg.get("listen_port") or self.allocated_listen_port(node, asn, data)),
            mtu=int(wg.get("mtu", 1420)),
            bgp_transport=transport,
            address_families=families,
            extended_next_hop=bool(bgp.get("extended_next_hop", False)),
            session_mode=session_mode,
            bgp=response_bgp,
            connection_info=PeerConnectionInfo.model_validate(
                self.connection_info(node, asn, transport, data)
            ),
        )

    def _validate_node_id(self, node: str) -> None:
        if "/" in node or ".." in node or not node:
            raise ValueError("invalid node id")
