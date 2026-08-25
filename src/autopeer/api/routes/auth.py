from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from autopeer.api.deps import get_current_principal
from autopeer.core.config import Settings, get_settings
from autopeer.core.security import Principal

router = APIRouter()


def _oidc_client(settings: Settings) -> OAuth:
    if not all((settings.oidc_discovery_url, settings.oidc_client_id, settings.oidc_client_secret)):
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    oauth = OAuth()
    oauth.register(
        name="kioubit",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=settings.oidc_discovery_url,
        client_kwargs={"scope": "openid profile"},
    )
    return oauth


def _asn_from_claims(claims: dict[str, Any], claim_name: str) -> int:
    raw_asn = claims.get(claim_name)
    try:
        asn = int(raw_asn)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=403, detail="OIDC identity has no valid ASN claim") from exc
    if not (1 <= asn <= 4_294_967_295):
        raise HTTPException(status_code=403, detail="OIDC ASN claim is outside the valid range")
    return asn


@router.get("/auth/login")
async def login(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is disabled")
    client = _oidc_client(settings).create_client("kioubit")
    assert client is not None
    return await client.authorize_redirect(request, request.url_for("auth_callback"))


@router.get("/auth/callback", name="auth_callback")
async def callback(
    request: Request, settings: Settings = Depends(get_settings)
) -> RedirectResponse:
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is disabled")
    client = _oidc_client(settings).create_client("kioubit")
    assert client is not None
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or await client.userinfo(token=token)
    asn = _asn_from_claims(claims, settings.oidc_asn_claim)
    request.session["principal_asn"] = asn
    return RedirectResponse(url="/")


@router.post("/auth/logout", status_code=204)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {"asn": principal.asn, "role": principal.role}
