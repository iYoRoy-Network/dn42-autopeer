from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml

from autopeer.domain.node import NodeSummary
from autopeer.domain.peer import (
    BgpTransport,
    BgpTransportMode,
    PeerResponse,
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
            dn42_vars = load_yaml(self.node_dir(node) / "bird-dn42.yml").get("dn42") or {}
            meta = node_vars.get("node") or {}
            deploy = node_vars.get("deploy") or {}
            peering = meta.get("peering") or {}
            nodes.append(
                NodeSummary(
                    id=node,
                    name=meta.get("name", node),
                    region=dn42_vars.get("region"),
                    country=dn42_vars.get("country"),
                    peering_enabled=bool(peering.get("enabled", True)),
                    deploy_bird_enabled=bool((deploy.get("bird") or {}).get("enabled", True)),
                    deploy_wireguard_enabled=bool(
                        (deploy.get("wireguard") or {}).get("enabled", False)
                    ),
                )
            )
        return nodes

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

    def build_peer_yaml(
        self,
        *,
        node: str,
        asn: int,
        description: str | None,
        public_key: str,
        endpoint: str,
        bgp_transport: BgpTransport,
        extended_next_hop: bool,
    ) -> dict[str, Any]:
        """Translate the narrow public API schema into the Ansible peer schema.

        User-provided values are limited to description, WireGuard public
        endpoint/key, BGP transport, and extended-next-hop. Operational fields
        such as listen_port, fwmark, src/dst, or lla are derived here.
        """
        wireguard: dict[str, Any] = {
            "public_key": public_key,
            "listen_port": listen_port_for_asn(asn),
            "fwmark": "4242",
            "endpoint": endpoint,
        }
        data: dict[str, Any] = {
            "description": description or f"AS{asn}",
            "asn": asn,
            "wireguard": wireguard,
        }
        if bgp_transport.mode == BgpTransportMode.ipv6_link_local:
            data["lla"] = bgp_transport.remote_address
        else:
            src = self.node_dn42_source(node, bgp_transport.mode)
            if not src:
                raise ValueError(f"node {node} has no source address for {bgp_transport.mode}")
            data["dst"] = bgp_transport.remote_address
            data["src"] = ipaddress.ip_address(src).compressed
        data["bgp"] = {"extended_next_hop": extended_next_hop}
        return data

    def peer_to_response(self, node: str, asn: int, data: dict[str, Any]) -> PeerResponse:
        wg = data.get("wireguard") or {}
        bgp = data.get("bgp") or {}
        if data.get("lla"):
            transport = BgpTransport(
                mode=BgpTransportMode.ipv6_link_local, remote_address=data["lla"]
            )
        elif data.get("dst"):
            ip = ipaddress.ip_address(data["dst"])
            mode = BgpTransportMode.ipv4 if ip.version == 4 else BgpTransportMode.ipv6
            transport = BgpTransport(mode=mode, remote_address=data["dst"])
        else:
            transport = BgpTransport(mode=BgpTransportMode.ipv6_link_local, remote_address="fe80::")
        return PeerResponse(
            node=node,
            asn=asn,
            description=data.get("description"),
            wireguard_public_key=wg.get("public_key", ""),
            wireguard_endpoint=wg.get("endpoint"),
            listen_port=int(wg.get("listen_port", listen_port_for_asn(asn))),
            bgp_transport=transport,
            address_families=["ipv4", "ipv6"],
            extended_next_hop=bool(bgp.get("extended_next_hop", False)),
        )

    def _validate_node_id(self, node: str) -> None:
        if "/" in node or ".." in node or not node:
            raise ValueError("invalid node id")
