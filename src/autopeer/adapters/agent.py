from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from autopeer.core.config import Settings


class AgentClient:
    """Send signed semantic peer requests to a node deployment agent."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.signing_key = self._load_signing_key(settings.agent_signing_private_key_file)

    def apply(
        self, agent_url: str, asn: int, payload: dict[str, object], *, method: str
    ) -> dict[str, object]:
        return self._request(agent_url, asn, payload, method)

    def delete(self, agent_url: str, asn: int) -> dict[str, object]:
        return self._request(agent_url, asn, {}, "DELETE")

    def _request(
        self, agent_url: str, asn: int, payload: dict[str, object], method: str
    ) -> dict[str, object]:
        parsed = urlparse(agent_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("node agent URL must be an HTTPS URL")
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        body_hash = hashlib.sha256(body).hexdigest()
        path = f"/api/v1/{asn}"
        signed = "\n".join((method, path, timestamp, nonce, body_hash)).encode()
        signature = base64.urlsafe_b64encode(self.signing_key.sign(signed)).rstrip(b"=").decode()
        headers = {
            "Content-Type": "application/json",
            "X-Autopeer-Timestamp": timestamp,
            "X-Autopeer-Nonce": nonce,
            "X-Autopeer-Body-SHA256": body_hash,
            "X-Autopeer-Signature": signature,
        }
        cert = None
        if self.settings.agent_client_cert_file and self.settings.agent_client_key_file:
            cert = (
                str(self.settings.agent_client_cert_file),
                str(self.settings.agent_client_key_file),
            )
        with httpx.Client(
            verify=self._ssl_context(cert),
            timeout=self.settings.agent_timeout_seconds,
        ) as client:
            response = client.request(
                method, agent_url.rstrip("/") + path, content=body, headers=headers
            )
        if response.is_error:
            raise RuntimeError(
                f"agent deployment failed ({response.status_code}): {response.text[-1000:]}"
            )
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("agent returned a non-object response")
        return result

    def _ssl_context(self, cert: tuple[str, str] | None) -> ssl.SSLContext:
        """Build the TLS context for agent requests.

        httpx returns early from create_ssl_context() when `verify` is a string
        path, so a `cert=` tuple passed alongside it is silently discarded and
        the handshake fails with "client didn't provide a certificate". Loading
        both the CA and the client chain onto one context avoids that.
        """
        if self.settings.agent_ca_file:
            context = ssl.create_default_context(cafile=str(self.settings.agent_ca_file))
        else:
            context = ssl.create_default_context()
        if cert:
            context.load_cert_chain(cert[0], cert[1])
        return context

    @staticmethod
    def _load_signing_key(path: Path | None) -> Ed25519PrivateKey:
        if path is None:
            raise ValueError("agent signing private key is not configured")
        data = path.read_bytes()
        if len(data) == 32:
            return Ed25519PrivateKey.from_private_bytes(data)
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("agent signing private key is not Ed25519")
        return key
