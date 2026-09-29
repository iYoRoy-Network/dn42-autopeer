import http.server
import ssl
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from autopeer.adapters.agent import AgentClient


@pytest.fixture(scope="module")
def ca_pem(tmp_path_factory) -> Path:
    """A real self-signed CA, since ssl rejects an empty cafile."""
    path = tmp_path_factory.mktemp("agenttls") / "ca.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(path.with_suffix(".key")),
            "-out",
            str(path),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=agent-test-ca",
        ],
        check=True,
        capture_output=True,
    )
    return path


def client_with(ca: Path | None, cert: Path | None, key: Path | None) -> AgentClient:
    # Bypass __init__ so the signing key material is not needed for TLS checks.
    client = AgentClient.__new__(AgentClient)
    client.settings = SimpleNamespace(
        agent_ca_file=ca,
        agent_client_cert_file=cert,
        agent_client_key_file=key,
        agent_timeout_seconds=15.0,
    )
    return client


def test_ssl_context_loads_client_certificate(ca_pem: Path):
    """The client chain must land on the context.

    httpx returns early from create_ssl_context() when `verify` is a string path,
    which silently discards a `cert=` tuple and makes the agent reject the
    handshake with "client didn't provide a certificate".
    """
    cert = ca_pem.with_suffix(".client.pem")
    key = ca_pem.with_suffix(".client.key")
    cert.write_text("")
    key.write_text("")

    loaded: list[tuple[str, str]] = []

    class SpyContext:
        def load_cert_chain(self, certfile, keyfile=None, password=None):
            loaded.append((str(certfile), str(keyfile)))

    real_create = ssl.create_default_context

    def fake_create_default_context(*args, **kwargs):
        return SpyContext()

    try:
        ssl.create_default_context = fake_create_default_context
        context = client_with(ca_pem, cert, key)._ssl_context((str(cert), str(key)))
    finally:
        ssl.create_default_context = real_create

    assert isinstance(context, SpyContext)
    assert loaded == [(str(cert), str(key))]


def test_ssl_context_without_client_certificate(ca_pem: Path):
    context = client_with(ca_pem, None, None)._ssl_context(None)

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_ssl_context_points_at_configured_ca(ca_pem: Path):
    seen: list[dict] = []
    real_create = ssl.create_default_context

    def fake_create_default_context(*args, **kwargs):
        seen.append(kwargs)
        return real_create(*args, **kwargs)

    try:
        ssl.create_default_context = fake_create_default_context
        client_with(ca_pem, None, None)._ssl_context(None)
    finally:
        ssl.create_default_context = real_create

    assert seen == [{"cafile": str(ca_pem)}]


def test_request_passes_ssl_context_not_a_path(ca_pem: Path, monkeypatch):
    """Guard the integration, not just the helper.

    Passing verify=<str path> is what made httpx drop the client certificate, so
    _request must hand a configured context to the transport.
    """
    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def request(self, *args, **kwargs):
            return httpx.Response(
                200, json={"status": "ok"}, request=httpx.Request("POST", "https://x")
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = client_with(ca_pem, None, None)
    client.signing_key = _signing_key()

    client._request("https://agent.test01.invalid", 4242420001, {}, "POST")

    assert isinstance(captured["verify"], ssl.SSLContext)
    assert "cert" not in captured


def _signing_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.generate()


def _request_client(ca: Path | None, cert: Path | None, key: Path | None) -> AgentClient:
    client = client_with(ca, cert, key)
    client.signing_key = _signing_key()
    return client


@pytest.fixture(scope="module")
def mtls_endpoint(tmp_path_factory):
    """A TLS 1.3 server that refuses connections without a client certificate.

    Mirrors the node agent's tls.Config (MinVersion TLS13, ClientAuth
    RequireAndVerifyClientCert) closely enough to exercise a real handshake.
    """
    directory = tmp_path_factory.mktemp("mtls")

    def openssl(*args: str) -> None:
        subprocess.run(("openssl", *args), check=True, capture_output=True)

    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(directory / "ca.key"),
        "-out",
        str(directory / "ca.pem"),
        "-days",
        "1",
        "-subj",
        "/CN=autopeer-test-ca",
    )
    (directory / "server.ext").write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=IP:127.0.0.1\n"
    )
    (directory / "client.ext").write_text(
        "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=clientAuth\n"
    )
    for name in ("server", "client"):
        openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(directory / f"{name}.key"),
            "-out",
            str(directory / f"{name}.csr"),
            "-subj",
            f"/CN={name}",
        )
        openssl(
            "x509",
            "-req",
            "-in",
            str(directory / f"{name}.csr"),
            "-CA",
            str(directory / "ca.pem"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(directory / f"{name}.pem"),
            "-days",
            "1",
            "-extfile",
            str(directory / f"{name}.ext"),
        )

    seen: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append(self.connection.getpeercert())
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(str(directory / "server.pem"), str(directory / "server.key"))
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(directory / "ca.pem"))

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield SimpleNamespace(
            url=f"https://127.0.0.1:{server.server_address[1]}",
            ca=directory / "ca.pem",
            cert=directory / "client.pem",
            key=directory / "client.key",
            seen=seen,
        )
    finally:
        server.shutdown()
        server.server_close()


def test_request_presents_client_certificate(mtls_endpoint):
    """The production failure: the agent logged "client didn't provide a
    certificate" and the backend saw TLSV13_ALERT_CERTIFICATE_REQUIRED."""
    client = _request_client(mtls_endpoint.ca, mtls_endpoint.cert, mtls_endpoint.key)

    result = client._request(mtls_endpoint.url, 4242420001, {}, "POST")

    assert result == {"status": "ok"}
    assert mtls_endpoint.seen and mtls_endpoint.seen[-1], (
        "the agent-side peer certificate was empty"
    )


def test_request_without_client_certificate_is_rejected(mtls_endpoint):
    """Keep the test above honest: the endpoint really does demand mTLS, so a
    client that fails to present a chain cannot silently pass."""
    client = _request_client(mtls_endpoint.ca, None, None)

    with pytest.raises(httpx.HTTPError):
        client._request(mtls_endpoint.url, 4242420001, {}, "POST")
