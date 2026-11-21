"""Shared fixtures for the e2e suite (pytest -m e2e; run by scripts/e2e.sh).

The suite talks to the MCP server the way a client does: a real MCP ClientSession over stdio
(`python -m src.server` as a subprocess) or over Streamable HTTP (the mcp-quickbuild-server
container). Without the variables below every test is skipped.

    E2E_QB_URL     QuickBuild as seen from this host, e.g. http://127.0.0.1:18810
    QB_USER / QB_PASSWORD
    E2E_STATE_DIR  harness state written by scripts/e2e.sh (fixtures.json, tls/ca.pem)
    E2E_MCP_URL    MCP endpoint of the HTTP container, e.g. http://127.0.0.1:14012/mcp
    E2E_TLS_URL    QuickBuild behind the HTTPS front, e.g. https://127.0.0.1:18843
"""
import base64
import json
import os
import re
import sys
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
              "http_proxy", "https_proxy", "all_proxy", "no_proxy")


class E2E:
    def __init__(self):
        self.qb_url = os.environ["E2E_QB_URL"].rstrip("/")
        self.user = os.environ["QB_USER"]
        self.password = os.environ["QB_PASSWORD"]
        self.state = Path(os.environ["E2E_STATE_DIR"])
        self.mcp_url = os.environ.get("E2E_MCP_URL", "")
        self.tls_url = os.environ.get("E2E_TLS_URL", "")
        self.ca_bundle = str(self.state / "tls" / "ca.pem")
        self.fixtures = json.loads((self.state / "fixtures.json").read_text())

    def rest(self, path: str, method: str = "GET", accept: str = "application/json"):
        """Direct QuickBuild REST call (test oracle, independent of the MCP server)."""
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        req = urllib.request.Request(
            f"{self.qb_url}/rest/{path}", method=method,
            headers={"Authorization": f"Basic {token}", "Accept": accept},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode()
        if accept == "application/json":
            return json.loads(text) if text.strip() else None
        return text

    def admin_access_token(self) -> str:
        """The admin's QuickBuild access token (User.accessToken in the user XML)."""
        xml = self.rest("users/1", accept="application/xml")
        match = re.search(r"<accessToken>([^<]+)</accessToken>", xml)
        assert match, "admin user has no access token"
        return match.group(1)

    def server_env(self, **overrides) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS and not k.startswith("QB_")}
        env.update({
            "QB_URL": self.qb_url, "QB_USER": self.user, "QB_PASSWORD": self.password,
            "QB_CACHE_TTL_CONFIGS": "0", "QB_CACHE_TTL_AGENTS": "0", "LOG_LEVEL": "WARNING",
            "MCP_TRANSPORT": "stdio",
        })
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env


@pytest.fixture(scope="session")
def e2e() -> E2E:
    if not os.environ.get("E2E_QB_URL"):
        pytest.skip("e2e harness not configured (run scripts/e2e.sh)")
    return E2E()


@asynccontextmanager
async def stdio_session(e2e: E2E, **env):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "src.server"], cwd=str(REPO_ROOT), env=e2e.server_env(**env)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@asynccontextmanager
async def http_session(url: str):
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call(session: ClientSession, name: str, arguments: dict | None = None):
    """Call a tool; return (is_error, parsed JSON payload)."""
    result = await session.call_tool(name, arguments or {})
    text = result.content[0].text
    try:
        payload = json.loads(text)
    except ValueError:
        payload = text
    return bool(result.is_error), payload


async def read(session: ClientSession, uri: str):
    result = await session.read_resource(uri)
    return json.loads(result.contents[0].text)
