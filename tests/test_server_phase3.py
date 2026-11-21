"""Tests for read-only mode, tool error reporting and the Streamable HTTP transport."""
import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.types import CallToolRequestParams, PaginatedRequestParams

from src import __version__
from src.config import Settings
from src.server import QuickBuildMCPServer, _is_error_payload

WRITE_TOOLS = {"builds.trigger", "build_requests.cancel", "system.backup_database"}
ALL_TOOLS = {
    "configurations.search",
    "builds.get_latest_status", "builds.get", "builds.get_log", "builds.list_running", "builds.trigger",
    "build_requests.list", "build_requests.cancel",
    "grid.list_agents", "grid.list_unauthorized",
    "system.backup_database", "system.get_version",
}


def make_server(**env) -> QuickBuildMCPServer:
    return QuickBuildMCPServer(Settings.from_env({"QB_PASSWORD": "pw", "QB_URL": "http://qb:8810", **env}))


async def listed_tools(server):
    handler = server.server.get_request_handler("tools/list")
    return {t.name for t in (await handler.handler(None, PaginatedRequestParams())).tools}


class TestToolCatalog:
    @pytest.mark.asyncio
    async def test_all_tools_listed_by_default(self):
        server = make_server()
        await server.setup()
        assert await listed_tools(server) == ALL_TOOLS
        assert server.disabled_tools == set()

    @pytest.mark.asyncio
    async def test_every_tool_is_annotated(self):
        server = make_server()
        await server.setup()
        for tool in server.tools:
            assert tool.annotations is not None, tool.name
            assert tool.annotations.read_only_hint is (tool.name not in WRITE_TOOLS), tool.name


class TestReadOnlyMode:
    @pytest.mark.asyncio
    async def test_write_tools_hidden(self, caplog):
        server = make_server(QB_READ_ONLY="true")
        with caplog.at_level(logging.INFO):
            await server.setup()
        assert await listed_tools(server) == ALL_TOOLS - WRITE_TOOLS
        assert server.disabled_tools == WRITE_TOOLS
        assert "write tools hidden and refused: build_requests.cancel, builds.trigger, system.backup_database" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool", sorted(WRITE_TOOLS))
    async def test_write_tools_refused_by_name_without_calling_quickbuild(self, tool):
        server = make_server(QB_READ_ONLY="true")
        await server.setup()
        server.qb_client = MagicMock()
        for feature in server.features:
            feature.qb_client = server.qb_client
        call = server.server.get_request_handler("tools/call")
        result = await call.handler(None, CallToolRequestParams(name=tool, arguments={"configuration_id": "1"}))
        assert result.is_error is True
        assert "QB_READ_ONLY=true" in json.loads(result.content[0].text)["error"]
        assert server.qb_client.mock_calls == []

    @pytest.mark.asyncio
    async def test_read_tools_still_work(self):
        server = make_server(QB_READ_ONLY="true")
        await server.setup()
        server.qb_client.get_version = AsyncMock(return_value={"version": "16.0.37"})
        for feature in server.features:
            feature.qb_client = server.qb_client
        result = await server.dispatch_tool_call("system.get_version", {})
        assert result.is_error is False
        assert json.loads(result.content[0].text) == {"version": "16.0.37"}


class TestErrorReporting:
    @pytest.mark.parametrize(
        "text, expected",
        [('{"error": "x"}', True), ('{"ok": 1}', False), ("[1]", False), ("plain", False), (None, False)],
    )
    def test_is_error_payload(self, text, expected):
        assert _is_error_payload(text) is expected

    @pytest.mark.asyncio
    async def test_feature_error_payload_sets_is_error(self):
        server = make_server()
        feature = AsyncMock()
        feature.handle_tool_call.return_value = json.dumps({"error": "Build 9 not found"})
        server.tool_handlers = {"builds.get": feature}
        result = await server.dispatch_tool_call("builds.get", {"build_id": "9"})
        assert result.is_error is True


class TestHttpTransport:
    @pytest.fixture
    async def http(self):
        server = make_server(MCP_TRANSPORT="http")
        await server.setup()
        app = server.build_http_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:14002") as client:
            yield server, client

    @pytest.mark.asyncio
    async def test_health(self, http):
        server, client = http
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok", "server": "quickbuild-mcp-server", "version": __version__,
            "transport": "http", "read_only": False,
        }

    @pytest.mark.asyncio
    async def test_ready_when_quickbuild_answers(self, http):
        server, client = http
        server.qb_client.get_version = AsyncMock(return_value={"version": "16.0.37"})
        response = await client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "quickbuild_version": "16.0.37"}

    @pytest.mark.asyncio
    async def test_not_ready_when_quickbuild_fails(self, http):
        server, client = http
        server.qb_client.get_version = AsyncMock(side_effect=RuntimeError("Cannot connect to QuickBuild server"))
        response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "error": "Cannot connect to QuickBuild server"}

    @pytest.mark.asyncio
    async def test_not_ready_on_timeout(self, http):
        server, client = http

        async def slow():
            await asyncio.sleep(5)

        server.qb_client.get_version = slow
        with patch("src.server.READY_TIMEOUT_SECONDS", 0.05):
            response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"] == "QuickBuild did not answer within 0.05s"

    def test_loopback_bind_uses_sdk_default_protection(self):
        assert make_server(MCP_TRANSPORT="http").transport_security() is None

    def test_wildcard_bind_without_allow_list_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert make_server(MCP_TRANSPORT="http", MCP_HOST="0.0.0.0").transport_security() is None
        assert "Host/Origin headers are not validated" in caplog.text

    @pytest.mark.asyncio
    async def test_allow_list_enforced(self):
        server = make_server(
            MCP_TRANSPORT="http", MCP_HOST="0.0.0.0",
            MCP_ALLOWED_HOSTS="mcp.corp:*", MCP_ALLOWED_ORIGINS="https://gw.corp",
        )
        security = server.transport_security()
        assert security.enable_dns_rebinding_protection is True
        assert security.allowed_hosts == ["mcp.corp:*"] and security.allowed_origins == ["https://gw.corp"]

        await server.setup()
        app = server.build_http_app()
        body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://evil.example:14002") as client:
            async with server.server.session_manager.run():
                rejected = await client.post("/mcp", json=body, headers=headers)
        assert rejected.status_code == 421

    @pytest.mark.asyncio
    async def test_run_selects_http(self):
        server = make_server(MCP_TRANSPORT="http")
        with patch.object(server, "_serve_http", new=AsyncMock()) as serve_http, \
                patch.object(server, "_serve_stdio", new=AsyncMock()) as serve_stdio, \
                patch.object(server.qb_client, "close", new=AsyncMock()):
            await server.run()
        serve_http.assert_awaited_once()
        serve_stdio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_serve_http_runs_uvicorn_on_configured_address(self):
        server = make_server(MCP_TRANSPORT="http", MCP_HOST="0.0.0.0", MCP_PORT="15001")
        await server.setup()
        with patch("uvicorn.Server.serve", new=AsyncMock()) as serve, \
                patch("uvicorn.Config.__init__", return_value=None) as config:
            await server._serve_http()
        serve.assert_awaited_once()
        assert config.call_args.kwargs["host"] == "0.0.0.0"
        assert config.call_args.kwargs["port"] == 15001


class TestContainerHealthcheck:
    def test_stdio_is_always_healthy(self):
        from src.healthcheck import check

        assert check({"MCP_TRANSPORT": "stdio"}) == 0
        assert check({}) == 0

    def test_http_probes_health_endpoint(self):
        from src import healthcheck

        response = MagicMock(status=200)
        response.__enter__.return_value = response
        with patch.object(healthcheck.urllib.request, "urlopen", return_value=response) as urlopen:
            assert healthcheck.check({"MCP_TRANSPORT": "http", "MCP_PORT": "15000"}) == 0
        assert urlopen.call_args.args[0] == "http://127.0.0.1:15000/health"

    def test_http_failure(self, capsys):
        from src import healthcheck

        with patch.object(healthcheck.urllib.request, "urlopen", side_effect=OSError("refused")):
            assert healthcheck.check({"MCP_TRANSPORT": "HTTP"}) == 1
        assert "health check failed: refused" in capsys.readouterr().err

    def test_http_non_200(self):
        from src import healthcheck

        response = MagicMock(status=503)
        response.__enter__.return_value = response
        with patch.object(healthcheck.urllib.request, "urlopen", return_value=response):
            assert healthcheck.check({"MCP_TRANSPORT": "http"}) == 1
