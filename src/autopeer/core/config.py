from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _csv_ints(value: str | list[int] | tuple[int, ...] | None) -> list[int]:
    """Parse comma-separated env values like AUTOPEER__ADMIN_ASNS=4242,4243."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    return [int(v) for v in value]


class Settings(BaseSettings):
    # All runtime knobs come from AUTOPEER__* environment variables or .env.
    # Nested delimiter is reserved for future grouped settings while keeping one flat class today.
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

    auth_mode: Literal["dev-header", "kioubit"] = "dev-header"
    # Admin role is configured outside Kioubit: any authenticated ASN in this
    # comma-separated allowlist receives cross-ASN operator permissions.
    # NoDecode lets the validator accept a human-friendly CSV rather than only
    # pydantic-settings' default JSON array environment representation.
    admin_asns: Annotated[list[int], NoDecode] = Field(default_factory=list)
    session_secret: str | None = None
    kioubit_domain: str | None = None
    kioubit_public_key_file: Path | None = None
    # Provider-supplied login page URL. Kioubit returns signed params/signature
    # values to /auth/callback rather than using an OpenID Connect code flow.
    kioubit_login_url: str | None = None

    metrics_targets_file: Path | None = None
    metrics_timeout_seconds: float = 5.0

    @field_validator("admin_asns", mode="before")
    @classmethod
    def parse_admin_asns(cls, value: object) -> list[int]:
        return _csv_ints(value)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Settings:
        if self.auth_mode != "kioubit":
            return self
        if not self.session_secret:
            raise ValueError("AUTOPEER__SESSION_SECRET is required when auth_mode=kioubit")
        if not self.kioubit_domain:
            raise ValueError("AUTOPEER__KIOUBIT_DOMAIN is required when auth_mode=kioubit")
        if not self.kioubit_public_key_file:
            raise ValueError("AUTOPEER__KIOUBIT_PUBLIC_KEY_FILE is required when auth_mode=kioubit")
        if not self.kioubit_public_key_file.is_file():
            raise ValueError("AUTOPEER__KIOUBIT_PUBLIC_KEY_FILE must reference a readable PEM file")
        return self

    @property
    def resolved_targeted_peer_playbook(self) -> Path:
        if self.targeted_peer_playbook is not None:
            return self.targeted_peer_playbook
        # The targeted deploy playbook belongs to the config repository so it
        # evolves with the same Ansible layout as the peer YAML it applies.
        return self.config_repo_path / "ansible" / "playbooks" / "deploy-dn42-peer.yml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
