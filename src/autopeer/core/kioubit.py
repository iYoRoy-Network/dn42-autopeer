from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


@dataclass(frozen=True)
class KioubitIdentity:
    """The intentionally small identity projection retained from Kioubit."""

    asn: int
    display_name: str | None


def effective_name(value: object) -> str | None:
    """Return a bounded display name without making a non-auth field authoritative."""
    if not isinstance(value, str):
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 160:
        return None
    return normalized


class KioubitAuthVerifier:
    """Verify Kioubit's signed login response and extract its ASN.

    Kioubit signs the base64-encoded ``params`` string, not the decoded JSON.
    The signature is checked with the provider's EC public key and SHA-512;
    freshness and domain checks prevent replaying a response for another site.
    The application retains only the ASN plus optional ``effective_name`` as a
    non-authoritative display name; all prefix, contact, maintainer, and token
    fields from the provider response are discarded.
    """

    def __init__(self, domain: str, public_key_file: Path | str):
        self.domain = domain.removeprefix("https://").removesuffix("/")
        public_key = Path(public_key_file).read_bytes()
        loaded_key = serialization.load_pem_public_key(public_key)
        if not isinstance(loaded_key, ec.EllipticCurvePublicKey):
            raise ValueError("Kioubit public key must be an EC public key")
        self.public_key = loaded_key

    def verify(self, params: str, signature: str, *, now: float | None = None) -> KioubitIdentity:
        try:
            encoded_signature = base64.b64decode(signature, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid base64 encoding for Kioubit signature") from exc

        try:
            self.public_key.verify(
                encoded_signature,
                params.encode("ascii"),
                ec.ECDSA(hashes.SHA512()),
            )
        except (InvalidSignature, UnicodeEncodeError) as exc:
            raise ValueError("invalid Kioubit signature") from exc

        try:
            decoded_params = base64.b64decode(params, validate=True)
            user_data = json.loads(decoded_params)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Kioubit params") from exc

        if not isinstance(user_data, dict):
            raise ValueError("Kioubit params must contain a JSON object")
        try:
            timestamp = float(user_data["time"])
            domain = str(user_data["domain"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Kioubit response is missing required fields") from exc

        if abs((time.time() if now is None else now) - timestamp) > 60:
            raise ValueError("Kioubit signature has expired")
        if domain != self.domain:
            raise ValueError("invalid Kioubit domain")

        try:
            asn = int(user_data["asn"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Kioubit response has no valid ASN") from exc
        if not 1 <= asn <= 4_294_967_295:
            raise ValueError("Kioubit ASN is outside the valid range")
        return KioubitIdentity(
            asn=asn, display_name=effective_name(user_data.get("effective_name"))
        )
