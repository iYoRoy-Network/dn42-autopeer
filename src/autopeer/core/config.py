from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv_ints(value: str | list[int] | tuple[int, ...] | None) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    return [int(v) for v in value]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTOPEER__",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "iyoroynet-autopeer"
    app_env: str = "dev"
    log_level: str = "INFO"

    database_path: Path = Path("/data/autopeer/jobs.sqlite3")
    config_repo_path: Path = Path("/config-repo")

    local_inventory: str = "ansible/inventory.yml"
    production_inventory: str = "ansible/inventory.production.yml"
    render_playbook: str = "ansible/playbooks/render.yml"
    validate_playbook: str = "ansible/playbooks/validate.yml"
    render_wireguard_playbook: str = "ansible/playbooks/render-wireguard.yml"
    validate_wireguard_playbook: str = "ansible/playbooks/validate-wireguard.yml"
    deploy_bird_playbook: str = "ansible/playbooks/deploy-bird.yml"
    deploy_wireguard_playbook: str = "ansible/playbooks/deploy-wireguard.yml"
    targeted_peer_playbook: Path | None = None

    command_timeout_seconds: int = 600
    deploy_enabled: bool = False
    targeted_deploy_enabled: bool = True
    git_push_enabled: bool = False
    git_sync_enabled: bool = False
    allow_dirty_repo: bool = False
    git_author_name: str = "Autopeer Bot"
    git_author_email: str = "autopeer@localhost"

    auth_mode: Literal["dev-header", "oidc"] = "dev-header"
    admin_asns: list[int] = Field(default_factory=list)
    session_secret: str | None = None
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_asn_claim: str = "asn"

    metrics_targets_file: Path | None = None
    metrics_timeout_seconds: float = 5.0

    @field_validator("admin_asns", mode="before")
    @classmethod
    def parse_admin_asns(cls, value: object) -> list[int]:
        return _csv_ints(value)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Settings:
        if self.auth_mode == "oidc" and not self.session_secret:
            raise ValueError("AUTOPEER__SESSION_SECRET is required when auth_mode=oidc")
        return self

    @property
    def resolved_targeted_peer_playbook(self) -> Path:
        if self.targeted_peer_playbook is not None:
            return self.targeted_peer_playbook
        return (
            Path(__file__).resolve().parents[3] / "ansible" / "playbooks" / "deploy-dn42-peer.yml"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
