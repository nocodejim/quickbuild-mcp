"""Corporate-readiness checks against the live harness: read-only mode, access-token auth,
TLS with a private CA, HTTPS through a forward proxy, and the HTTP transport's endpoints."""
import json
import os
import select
import socket
import socketserver
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from src.config import Settings
from src.exceptions import QuickBuildUnavailableError
from src.quickbuild_client import QuickBuildClient
from tests.e2e.conftest import call, stdio_session

pytestmark = pytest.mark.e2e

WRITE_TOOLS = {"builds.trigger", "build_requests.cancel", "system.backup_database"}


# ---------------------------------------------------------------- read-only mode

async def test_read_only_hides_and_refuses_write_tools(e2e):
    f = e2e.fixtures
    queued_before = e2e.rest(f"build_requests?configuration_id={f['sleep_config_id']}")
    latest_before = e2e.rest(f"latest_builds/{f['sleep_config_id']}")
    async with stdio_session(e2e, QB_READ_ONLY="true") as session:
        tools = {t.name for t in (await session.list_tools()).tools}
        assert tools.isdisjoint(WRITE_TOOLS)
        assert "builds.get" in tools

        for name, args in [
            ("builds.trigger", {"configuration_id": f["sleep_config_id"]}),
            ("build_requests.cancel", {"request_id": "00000000-0000-0000-0000-000000000000"}),
            ("system.backup_database", {}),
        ]:
            is_error, payload = await call(session, name, args)
            assert is_error and "QB_READ_ONLY=true" in payload["error"], name

        is_error, _ = await call(session, "builds.get", {"build_id": f["changes_build_id"]})
        assert not is_error
    # Nothing reached QuickBuild: no new request, no new build
    assert e2e.rest(f"build_requests?configuration_id={f['sleep_config_id']}") == queued_before
    assert e2e.rest(f"latest_builds/{f['sleep_config_id']}") == latest_before


# ---------------------------------------------------------------- access token auth

async def test_access_token_auth(e2e):
    token = e2e.admin_access_token()
    async with stdio_session(e2e, QB_AUTH_MODE="token", QB_TOKEN=token, QB_PASSWORD=None) as session:
        is_error, version = await call(session, "system.get_version")
        assert not is_error and version["version"].startswith("16.")
    async with stdio_session(e2e, QB_AUTH_MODE="token", QB_TOKEN=token[:-1] + "x", QB_PASSWORD=None) as session:
        is_error, payload = await call(session, "system.get_version")
        assert is_error and "QB_USER/QB_TOKEN" in payload["error"]


async def test_password_file(e2e, tmp_path):
    secret = tmp_path / "qb-password"
    secret.write_text(e2e.password + "\n")
    async with stdio_session(e2e, QB_PASSWORD=None, QB_PASSWORD_FILE=str(secret)) as session:
        is_error, _ = await call(session, "system.get_version")
        assert not is_error


# ---------------------------------------------------------------- TLS with a private CA

def tls_client(e2e, **env) -> QuickBuildClient:
    values = {"QB_URL": e2e.tls_url, "QB_USER": e2e.user, "QB_PASSWORD": e2e.password, **env}
    clean = {k: v for k, v in os.environ.items() if not k.upper().endswith("_PROXY")}
    with patch.dict(os.environ, {**clean, **{k: v for k, v in values.items() if k.upper().endswith("_PROXY")}}, clear=True):
        return QuickBuildClient(settings=Settings.from_env(values))


@pytest.fixture
def tls(e2e):
    if not e2e.tls_url:
        pytest.skip("E2E_TLS_URL not set")
    return e2e


async def test_tls_untrusted_without_ca_bundle(tls):
    async with tls_client(tls) as client:
        with pytest.raises(QuickBuildUnavailableError) as exc:
            await client.get_version()
    assert exc.value.error_code == "TLS_VERIFY_FAILED"
    assert "QB_CA_BUNDLE" in str(exc.value)


async def test_tls_trusted_with_ca_bundle(tls):
    async with tls_client(tls, QB_CA_BUNDLE=tls.ca_bundle) as client:
        assert (await client.get_version())["version"].startswith("16.")
        log = await client.get_build_log(tls.fixtures["changes_build_id"], tail_lines=3)
        assert log["line_count"] == 3


async def test_tls_verification_disabled(tls):
    async with tls_client(tls, QB_VERIFY_SSL="false") as client:
        assert (await client.get_version())["version"].startswith("16.")


async def test_mcp_server_over_tls_with_ca_bundle(tls):
    async with stdio_session(tls, QB_URL=tls.tls_url, QB_CA_BUNDLE=tls.ca_bundle) as session:
        is_error, version = await call(session, "system.get_version")
        assert not is_error and version["version"].startswith("16.")


# ---------------------------------------------------------------- HTTPS through a proxy

class _ConnectProxy(socketserver.ThreadingTCPServer):
    """Minimal HTTP CONNECT proxy (like a corporate egress proxy); records tunnel targets."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        self.targets = []
        super().__init__(("127.0.0.1", 0), _ConnectHandler)


class _ConnectHandler(socketserver.StreamRequestHandler):
    def handle(self):
        request_line = self.rfile.readline().decode("latin-1").strip()
        while self.rfile.readline() not in (b"\r\n", b"\n", b""):
            pass
        method, target, _ = request_line.split(" ", 2)
        if method != "CONNECT":
            self.wfile.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        self.server.targets.append(target)
        host, port = target.rsplit(":", 1)
        upstream = socket.create_connection((host, int(port)), timeout=30)
        self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        self.wfile.flush()
        sockets = [self.connection, upstream]
        try:
            while True:
                ready, _, _ = select.select(sockets, [], [], 30)
                if not ready:
                    break
                for sock in ready:
                    data = sock.recv(65536)
                    if not data:
                        return
                    (upstream if sock is self.connection else self.connection).sendall(data)
        finally:
            upstream.close()


@contextmanager
def connect_proxy():
    proxy = _ConnectProxy()
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        yield proxy
    finally:
        proxy.shutdown()
        proxy.server_close()


async def test_https_proxy_is_used(tls):
    with connect_proxy() as proxy:
        proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
        async with tls_client(tls, QB_CA_BUNDLE=tls.ca_bundle, HTTPS_PROXY=proxy_url) as client:
            assert (await client.get_version())["version"].startswith("16.")
        tls_host = tls.tls_url.split("://", 1)[1]
        assert tls_host in proxy.targets


async def test_no_proxy_bypasses_proxy(tls):
    with connect_proxy() as proxy:
        proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
        async with tls_client(tls, QB_CA_BUNDLE=tls.ca_bundle, HTTPS_PROXY=proxy_url, NO_PROXY="127.0.0.1") as client:
            assert (await client.get_version())["version"].startswith("16.")
        assert proxy.targets == []


# ---------------------------------------------------------------- HTTP transport endpoints

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_container_health_ready_and_host_allow_list(e2e):
    if not e2e.mcp_url:
        pytest.skip("E2E_MCP_URL not set")
    base = e2e.mcp_url.rsplit("/", 1)[0]
    status, body = http_get(f"{base}/health")
    assert status == 200 and json.loads(body)["status"] == "ok"
    status, body = http_get(f"{base}/ready")
    assert status == 200 and json.loads(body)["quickbuild_version"].startswith("16.")

    # MCP_ALLOWED_HOSTS=127.0.0.1:*,localhost:* in the e2e stack: a foreign Host header is refused
    req = urllib.request.Request(
        e2e.mcp_url, method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode(),
        headers={"Host": "evil.example:14012", "Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=15)
    assert exc.value.code == 421
