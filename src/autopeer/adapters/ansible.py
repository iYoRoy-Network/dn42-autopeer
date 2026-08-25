from __future__ import annotations

import subprocess
from dataclasses import dataclass

from autopeer.core.config import Settings


@dataclass
class CommandResult:
    argv: list[str]
    rc: int
    stdout: str
    stderr: str


class AnsibleRunner:
    """Boundary for external ansible-playbook calls.

    Business code decides what should happen; this adapter only builds command
    lines, runs them from the config repository, applies timeouts, and redacts
    failures before they are stored in job errors.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo_root = settings.config_repo_path

    def _run(self, argv: list[str], timeout: int | None = None) -> CommandResult:
        result = subprocess.run(
            argv,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            timeout=timeout or self.settings.command_timeout_seconds,
            check=False,
        )
        command = CommandResult(
            argv=argv, rc=result.returncode, stdout=result.stdout, stderr=result.stderr
        )
        if result.returncode != 0:
            raise RuntimeError(self._redact(command.stderr or command.stdout))
        return command

    def render_and_validate(
        self,
        node: str,
        *,
        render_wireguard: bool,
    ) -> list[CommandResult]:
        commands = [
            [
                "ansible-playbook",
                "-i",
                self.settings.local_inventory,
                self.settings.render_playbook,
                "--limit",
                node,
            ],
            [
                "ansible-playbook",
                "-i",
                self.settings.local_inventory,
                self.settings.validate_playbook,
                "--limit",
                node,
            ],
        ]
        if render_wireguard:
            commands.extend(
                [
                    [
                        "ansible-playbook",
                        "-i",
                        self.settings.local_inventory,
                        self.settings.render_wireguard_playbook,
                        "--limit",
                        node,
                    ],
                    [
                        "ansible-playbook",
                        "-i",
                        self.settings.local_inventory,
                        self.settings.validate_wireguard_playbook,
                        "--limit",
                        node,
                    ],
                ]
            )
        return [self._run(command) for command in commands]

    def deploy_host(
        self, node: str, *, apply_wireguard: bool, apply_bird: bool
    ) -> list[CommandResult]:
        commands: list[list[str]] = []
        if apply_wireguard:
            commands.append(
                [
                    "ansible-playbook",
                    "-i",
                    self.settings.production_inventory,
                    self.settings.deploy_wireguard_playbook,
                    "--limit",
                    node,
                ]
            )
        if apply_bird:
            commands.append(
                [
                    "ansible-playbook",
                    "-i",
                    self.settings.production_inventory,
                    self.settings.deploy_bird_playbook,
                    "--limit",
                    node,
                ]
            )
        return [self._run(command) for command in commands]

    def deploy_peer(
        self, node: str, asn: int, *, state: str, apply_wireguard: bool, apply_bird: bool
    ) -> list[CommandResult]:
        playbook = self.settings.resolved_targeted_peer_playbook
        argv = [
            "ansible-playbook",
            "-i",
            self.settings.production_inventory,
            str(playbook),
            "--limit",
            node,
            "-e",
            f"target_peer_asn={asn}",
            "-e",
            f"target_peer_state={state}",
            "-e",
            f"apply_wireguard={str(apply_wireguard).lower()}",
            "-e",
            f"apply_bird={str(apply_bird).lower()}",
        ]
        return [self._run(argv)]

    def _redact(self, text: str) -> str:
        # Do not persist raw Ansible output: rendered WireGuard/BIRD files can contain secrets.
        lines = [
            line
            for line in text.splitlines()
            if "preshared" not in line.lower() and "privatekey" not in line.lower()
        ]
        return "\n".join(lines[-80:])[-4000:]
