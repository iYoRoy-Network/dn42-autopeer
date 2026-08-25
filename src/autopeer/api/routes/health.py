from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    repo_ok = (settings.config_repo_path / "ansible").is_dir()
    return {"status": "ok" if repo_ok else "degraded", "config_repo": repo_ok}
