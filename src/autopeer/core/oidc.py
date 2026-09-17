from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from autopeer.core.kioubit import effective_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OIDCIdentity:
    asn: int
    display_name: str | None


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _claim_asn(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("OIDC dn42 claim is not a valid ASN")
    if isinstance(value, dict):
        value = value.get("asn")
    if isinstance(value, str):
        value = value.strip()
        if value.upper().startswith("AS"):
            value = value[2:].strip()
    try:
        asn = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OIDC dn42 claim is not a valid ASN") from exc
    if not 4_242_420_001 <= asn <= 4_242_423_999:
        raise ValueError("OIDC ASN is outside the supported range")
    return asn


class OIDCClient:
    def __init__(self, issuer: str, client_id: str, client_secret: str | None = None):
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._metadata: dict[str, object] | None = None

    def metadata(self, client: httpx.Client) -> dict[str, object]:
        if self._metadata is None:
            response = client.get(f"{self.issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("OIDC discovery response is invalid")
            self._metadata = data
        return self._metadata

    @staticmethod
    def create_login_state() -> dict[str, str]:
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return {
            "state": secrets.token_urlsafe(32),
            "nonce": secrets.token_urlsafe(32),
            "verifier": verifier,
            "challenge": challenge,
        }

    def authorization_url(
        self, redirect_uri: str, state: dict[str, str], client: httpx.Client
    ) -> str:
        metadata = self.metadata(client)
        endpoint = metadata.get("authorization_endpoint")
        if not isinstance(endpoint, str):
            raise ValueError("OIDC discovery has no authorization endpoint")
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email dn42",
            "state": state["state"],
            "nonce": state["nonce"],
            "code_challenge": state["challenge"],
            "code_challenge_method": "S256",
        }
        return f"{endpoint}?{urlencode(query)}"

    def exchange(
        self, code: str, redirect_uri: str, verifier: str, client: httpx.Client
    ) -> dict[str, object]:
        metadata = self.metadata(client)
        endpoint = metadata.get("token_endpoint")
        if not isinstance(endpoint, str):
            raise ValueError("OIDC discovery has no token endpoint")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        auth = (self.client_id, self.client_secret) if self.client_secret else None
        if auth is None:
            data["client_id"] = self.client_id
        response = client.post(endpoint, data=data, auth=auth)
        logger.debug("OIDC token endpoint response: status=%s", response.status_code)
        response.raise_for_status()
        token = response.json()
        if isinstance(token, dict):
            logger.debug("OIDC token response fields: %s", sorted(token))
        if not isinstance(token, dict) or not isinstance(token.get("id_token"), str):
            raise ValueError("OIDC token response has no ID token")
        return token

    def verify_id_token(self, token: str, nonce: str, client: httpx.Client) -> OIDCIdentity:
        try:
            header_raw, payload_raw, signature_raw = token.split(".")
            header = json.loads(_b64decode(header_raw))
            claims = json.loads(_b64decode(payload_raw))
            signature = _b64decode(signature_raw)
            if isinstance(claims, dict):
                logger.debug(
                    "OIDC ID token claims: iss=%r aud_type=%s aud=%r nonce_present=%s exp=%r dn42=%r dn42_type=%s name=%r preferred_username=%r",
                    claims.get("iss"),
                    type(claims.get("aud")).__name__,
                    claims.get("aud"),
                    bool(claims.get("nonce")),
                    claims.get("exp"),
                    claims.get("dn42"),
                    type(claims.get("dn42")).__name__,
                    claims.get("name"),
                    claims.get("preferred_username"),
                )
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("OIDC ID token is malformed") from exc
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError("OIDC ID token uses an unsupported signing algorithm")
        metadata = self.metadata(client)
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise ValueError("OIDC discovery has no JWKS URI")
        response = client.get(jwks_uri)
        response.raise_for_status()
        keys = response.json().get("keys", [])
        jwk = next((key for key in keys if key.get("kid") == header["kid"]), None)
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA":
            raise ValueError("OIDC signing key is unavailable")
        try:
            public_key = rsa.RSAPublicNumbers(
                int.from_bytes(_b64decode(jwk["e"]), "big"),
                int.from_bytes(_b64decode(jwk["n"]), "big"),
            ).public_key()
            public_key.verify(
                signature,
                f"{header_raw}.{payload_raw}".encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (KeyError, ValueError, TypeError, InvalidSignature, OverflowError) as exc:
            raise ValueError("invalid OIDC ID token signature") from exc
        if claims.get("iss") != self.issuer:
            raise ValueError("invalid OIDC issuer")
        audience = claims.get("aud")
        if not (
            audience == self.client_id or isinstance(audience, list) and self.client_id in audience
        ):
            raise ValueError("invalid OIDC audience")
        if claims.get("nonce") != nonce:
            raise ValueError("invalid OIDC nonce")
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= time.time():
            raise ValueError("OIDC ID token has expired")
        return OIDCIdentity(
            _claim_asn(claims.get("dn42")),
            effective_name(claims.get("name") or claims.get("preferred_username")),
        )
