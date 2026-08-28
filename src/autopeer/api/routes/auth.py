from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from autopeer.api.deps import get_current_principal
from autopeer.core.config import Settings, get_settings
from autopeer.core.kioubit import KioubitAuthVerifier
from autopeer.core.security import Principal

router = APIRouter()


def _kioubit_verifier(settings: Settings) -> KioubitAuthVerifier:
    if not settings.kioubit_domain or not settings.kioubit_public_key_file:
        raise HTTPException(status_code=503, detail="Kioubit authentication is not configured")
    try:
        return KioubitAuthVerifier(settings.kioubit_domain, settings.kioubit_public_key_file)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Kioubit public key is unavailable") from exc


@router.get("/auth/callback")
def callback(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if settings.auth_mode != "kioubit":
        raise HTTPException(status_code=404, detail="Kioubit login is disabled")
    params = request.query_params.get("params")
    signature = request.query_params.get("signature")
    if not params or not signature:
        raise HTTPException(status_code=400, detail="Kioubit params and signature are required")
    # URL query parsers decode an unescaped base64 '+' as a space. A signed
    # Kioubit value is standard base64, where literal spaces are invalid, so
    # normalize it before verifying without altering the signed value otherwise.
    params = params.replace(" ", "+")
    signature = signature.replace(" ", "+")
    try:
        identity = _kioubit_verifier(settings).verify(params, signature)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    request.session["principal_asn"] = identity.asn
    request.session["principal_display_name"] = identity.display_name
    return RedirectResponse(url="/")


@router.post("/auth/logout", status_code=204)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {
        "asn": principal.asn,
        "role": principal.role,
        "display_name": principal.display_name,
    }
