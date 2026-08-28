from __future__ import annotations

from pathlib import Path
from typing import Any

from autopeer.adapters.ansible import AnsibleRunner
from autopeer.adapters.git import GitClient
from autopeer.adapters.repository import ConfigRepository
from autopeer.core.config import Settings
from autopeer.core.security import Principal
from autopeer.domain.errors import ConflictError, NotFoundError
from autopeer.domain.peer import (
    PeerCreateRequest,
    PeerPatchRequest,
    PeerResponse,
    validate_dn42_autopeer_asn,
)


class PeerService:
    """Application use-case layer for self-service DN42 peer mutations.

    API routes only authorize and enqueue jobs. The worker calls this service to
    serialize the side effects: validate ownership/node state, update one peer
    YAML file, commit to Git, and optionally run the peer-scoped render/deploy playbook.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = ConfigRepository(settings.config_repo_path)
        self.git = GitClient(
            settings.config_repo_path,
            author_name=settings.git_author_name,
            author_email=settings.git_author_email,
        )
        self.ansible = AnsibleRunner(settings)

    def list_nodes(self):
        self.repo.ensure_exists()
        return self.repo.list_nodes()

    def list_node_ids(self) -> list[str]:
        self.repo.ensure_exists()
        return self.repo.list_inventory_nodes()

    def list_peers_for_principal(self, node: str, principal: Principal) -> list[PeerResponse]:
        self.repo.require_node(node)
        peers = self.repo.list_peers(node)
        if principal.is_admin:
            return peers
        return [peer for peer in peers if peer.asn == principal.asn]

    def get_peer(self, node: str, asn: int, principal: Principal) -> PeerResponse:
        principal.require_peer_access(asn)
        data = self.repo.read_peer(node, asn)
        if data is None:
            raise NotFoundError(f"peer AS{asn} on {node} not found")
        return self.repo.peer_to_response(node, asn, data)

    def execute_peer_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation = payload["operation"]
        node = payload["node"]
        asn = int(payload["asn"])
        validate_dn42_autopeer_asn(asn)
        self.repo.require_node(node)
        node_summary = next(item for item in self.repo.list_nodes() if item.id == node)
        if not node_summary.peering_enabled:
            raise PermissionError(f"peering is disabled on node {node}")

        if self.settings.git_sync_enabled:
            self.git.assert_clean_or_only([], self.settings.allow_dirty_repo)
            self.git.pull_ff_only()

        peer_path = self.repo.peer_file(node, asn)
        changed_paths: list[Path] = [peer_path]
        apply_wireguard = False
        apply_bird = False
        target_state = "present"

        existing = self.repo.read_peer(node, asn)
        if operation == "delete":
            if existing is None:
                raise NotFoundError(f"peer AS{asn} on {node} not found")
            self.repo.delete_peer(node, asn)
            target_state = "absent"
            apply_wireguard = True
            apply_bird = True
        else:
            if operation == "create" and existing is not None:
                raise ConflictError(f"peer AS{asn} on {node} already exists")
            if operation == "update" and existing is None:
                raise NotFoundError(f"peer AS{asn} on {node} not found")
            request = self._request_from_payload(operation, payload["data"])
            data = self._merge_peer(node=node, asn=asn, existing=existing, request=request)
            self.repo.write_peer(node, asn, data)
            apply_wireguard = self._operation_touches_wireguard(operation, payload["data"])
            apply_bird = self._operation_touches_bird(operation, payload["data"])

        self.git.assert_clean_or_only(changed_paths, self.settings.allow_dirty_repo)

        # The targeted playbook renders only this peer's BIRD and WireGuard
        # artifacts immediately before applying them; do not run host-wide
        # render or validate playbooks for a self-service peer mutation.
        commit_sha = self.git.add_and_commit(
            changed_paths,
            f"autopeer({node}): {operation} AS{asn}",
        )
        if commit_sha and self.settings.git_push_enabled:
            self.git.push()

        deploy_result = "skipped"
        if self.settings.deploy_enabled:
            # This playbook is deliberately peer-scoped, including its render
            # step; never widen a self-service mutation when targeted deploy is enabled.
            if self.settings.targeted_deploy_enabled:
                self.ansible.deploy_peer(
                    node,
                    asn,
                    state=target_state,
                    apply_wireguard=apply_wireguard,
                    apply_bird=apply_bird,
                )
                deploy_result = "targeted"
            else:
                self.ansible.deploy_host(node, apply_wireguard=True, apply_bird=True)
                deploy_result = "host"

        result = {
            "operation": operation,
            "node": node,
            "asn": asn,
            "commit_sha": commit_sha,
            "deploy": deploy_result,
            "state": target_state,
        }
        if target_state == "present":
            result["peer"] = self.repo.peer_to_response(
                node,
                asn,
                self.repo.read_peer(node, asn) or {},
            ).model_dump(mode="json")
        return result

    def _request_from_payload(
        self, operation: str, data: dict[str, Any]
    ) -> PeerCreateRequest | PeerPatchRequest:
        if operation == "create":
            return PeerCreateRequest.model_validate(data)
        return PeerPatchRequest.model_validate(data)

    def _merge_peer(
        self,
        *,
        node: str,
        asn: int,
        existing: dict[str, Any] | None,
        request: PeerCreateRequest | PeerPatchRequest,
    ) -> dict[str, Any]:
        if isinstance(request, PeerCreateRequest):
            return self.repo.build_peer_yaml(
                node=node,
                asn=asn,
                description=request.description,
                public_key=request.wireguard.public_key,
                endpoint=request.wireguard.endpoint,
                bgp_transport=request.bgp.transport,
                extended_next_hop=request.bgp.extended_next_hop,
                listen_port=self.repo.allocated_listen_port(node, asn),
            )

        assert existing is not None
        wg = existing.setdefault("wireguard", {})
        bgp = existing.setdefault("bgp", {})
        if "description" in request.model_fields_set:
            existing["description"] = request.description or f"AS{asn}"
        if request.wireguard is not None:
            if (
                "public_key" in request.wireguard.model_fields_set
                and request.wireguard.public_key is not None
            ):
                wg["public_key"] = request.wireguard.public_key
            if (
                "endpoint" in request.wireguard.model_fields_set
                and request.wireguard.endpoint is not None
            ):
                wg["endpoint"] = request.wireguard.endpoint
        wg["listen_port"] = self.repo.allocated_listen_port(node, asn, existing)
        if request.bgp is not None:
            if request.bgp.transport is not None:
                rebuilt = self.repo.build_peer_yaml(
                    node=node,
                    asn=asn,
                    description=existing.get("description"),
                    public_key=wg["public_key"],
                    endpoint=wg["endpoint"],
                    bgp_transport=request.bgp.transport,
                    extended_next_hop=bool(bgp.get("extended_next_hop", True)),
                )
                existing.pop("lla", None)
                existing.pop("dst", None)
                existing.pop("src", None)
                for key in ("lla", "dst", "src"):
                    if key in rebuilt:
                        existing[key] = rebuilt[key]
            if request.bgp.extended_next_hop is not None:
                bgp["extended_next_hop"] = request.bgp.extended_next_hop
        existing["asn"] = asn
        return existing

    def _operation_touches_wireguard(self, operation: str, data: dict[str, Any]) -> bool:
        return operation == "create" or "wireguard" in data

    def _operation_touches_bird(self, operation: str, data: dict[str, Any]) -> bool:
        return operation == "create" or any(key in data for key in ("description", "bgp"))
