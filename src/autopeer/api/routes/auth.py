from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from autopeer.api.deps import get_current_principal
from autopeer.core.config import Settings, get_settings
from autopeer.core.oidc import OIDCClient
from autopeer.core.security import Principal

router = APIRouter()


def _oidc_client(settings: Settings) -> OIDCClient:
    if not settings.oidc_client_id or not settings.oidc_redirect_uri:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured")
    secret = settings.oidc_client_secret
    if settings.oidc_client_secret_file:
        try:
            secret = settings.oidc_client_secret_file.read_text().strip()
        except OSError as exc:
            raise HTTPException(
                status_code=503, detail="OIDC client secret is unavailable"
            ) from exc
    return OIDCClient(settings.oidc_issuer, settings.oidc_client_id, secret)


@router.get("/auth/login")
def login(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is disabled")
    state = OIDCClient.create_login_state()
    request.session["oidc_state"] = state["state"]
    request.session["oidc_nonce"] = state["nonce"]
    request.session["oidc_verifier"] = state["verifier"]
    try:
        with httpx.Client(timeout=10) as client:
            url = _oidc_client(settings).authorization_url(
                settings.oidc_redirect_uri, state, client
            )
    except Exception as exc:
        request.session.pop("oidc_state", None)
        request.session.pop("oidc_nonce", None)
        request.session.pop("oidc_verifier", None)
        raise HTTPException(status_code=503, detail="OIDC provider is unavailable") from exc
    return RedirectResponse(url=url, status_code=302)


@router.get("/auth/callback")
def callback(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if settings.auth_mode == "oidc":
        error = request.query_params.get("error")
        state = request.query_params.get("state")
        code = request.query_params.get("code")
        expected_state = request.session.pop("oidc_state", None)
        nonce = request.session.pop("oidc_nonce", None)
        verifier = request.session.pop("oidc_verifier", None)
        if error:
            raise HTTPException(status_code=400, detail="OIDC authorization was denied")
        if not code or not state or not isinstance(expected_state, str) or state != expected_state:
            raise HTTPException(status_code=401, detail="invalid OIDC state")
        if not isinstance(nonce, str) or not isinstance(verifier, str):
            raise HTTPException(status_code=401, detail="OIDC login session is missing")
        try:
            oidc = _oidc_client(settings)
            with httpx.Client(timeout=10) as client:
                token = oidc.exchange(code, settings.oidc_redirect_uri, verifier, client)
                identity = oidc.verify_id_token(token["id_token"], nonce, client)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="OIDC authentication failed") from exc
        request.session["principal_asn"] = identity.asn
        request.session["principal_display_name"] = identity.display_name
        return RedirectResponse(url="/")
    raise HTTPException(status_code=404, detail="Login callback is disabled")


@router.post("/auth/logout", status_code=204)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {"asn": principal.asn, "role": principal.role, "display_name": principal.display_name}
