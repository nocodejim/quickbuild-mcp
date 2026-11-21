"""
Tests for MCP server
"""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import (
    CallToolRequestParams,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    Resource,
    ResourceTemplate,
    TextContent,
    Tool,
)

from src.features.build_requests.feature import BuildRequestsFeature
from src.features.builds.feature import BuildsFeature
from src.features.changes.feature import ChangesFeature
from src.features.configurations.feature import ConfigurationsFeature
from src.features.grid.feature import GridFeature
from src.features.system.feature import SystemFeature
from src.server import QuickBuildMCPServer


class TestQuickBuildMCPServer:
    """Test QuickBuildMCPServer"""

    @pytest.fixture
    def server(self):
        """Create server for testing"""
        with patch.dict(
            os.environ,
            {
                "QB_URL": "http://test:8810",
                "QB_USER": "testuser",
                "QB_PASSWORD": "testpass",
            },
        ):
            return QuickBuildMCPServer()

    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.server is not None
        assert server.qb_client is not None
        assert server.features == []
        assert server.tool_handlers == {}
        assert server.resource_handlers == {}
        assert server.resource_template_handlers == []

    def test_load_features(self, server):
        """Test loading all 6 feature modules"""
        features = server.load_features()

        assert [type(f) for f in features] == [
            ConfigurationsFeature,
            BuildsFeature,
            BuildRequestsFeature,
            GridFeature,
            ChangesFeature,
            SystemFeature,
        ]

    @pytest.mark.asyncio
    async def test_setup_success(self, server):
        """Test successful server setup registers MCP v2 request handlers"""
        mock_tool = Tool(
            name="test.tool",
            description="Test tool",
            input_schema={"type": "object"},
        )
        mock_resource = Resource(
            uri="test://resource",
            name="Test Resource",
            mime_type="text/plain",
        )
        mock_template = ResourceTemplate(
            uri_template="test://item/{id}",
            name="Test Template",
            mime_type="application/json",
        )

        mock_feature = MagicMock()
        mock_feature.get_tools.return_value = [mock_tool]
        mock_feature.get_resources.return_value = [mock_resource]
        mock_feature.get_resource_templates.return_value = [mock_template]

        with patch.object(server, "load_features", return_value=[mock_feature]):
            await server.setup()

            assert len(server.features) == 1
            assert server.tool_handlers["test.tool"] == mock_feature
            assert "test://resource" in server.resource_handlers
            assert ("test://item/", mock_feature) in server.resource_template_handlers

            assert server.server.get_request_handler("tools/list") is not None
            assert server.server.get_request_handler("tools/call") is not None
            assert server.server.get_request_handler("resources/list") is not None
            assert server.server.get_request_handler("resources/templates/list") is not None
            assert server.server.get_request_handler("resources/read") is not None

    @pytest.mark.asyncio
    async def test_setup_with_error(self, server):
        """Test server setup with error"""
        with patch.object(server, "load_features", side_effect=Exception("Setup error")):
            with pytest.raises(Exception, match="Setup error"):
                await server.setup()

    @pytest.mark.asyncio
    async def test_mcp_protocol_handlers_dispatch(self, server):
        """Test registered MCP v2 request handlers invoke tools, resources, and templates"""
        mock_tool = Tool(
            name="test.tool",
            description="Test tool",
            input_schema={"type": "object"},
        )
        mock_resource = Resource(
            uri="test://resource",
            name="Test Resource",
            mime_type="application/json",
        )
        mock_template = ResourceTemplate(
            uri_template="changes://build/{build_id}",
            name="Build Changes",
            mime_type="application/json",
        )

        mock_feature = AsyncMock()
        mock_feature.get_tools = MagicMock(return_value=[mock_tool])
        mock_feature.get_resources = MagicMock(return_value=[mock_resource])
        mock_feature.get_resource_templates = MagicMock(return_value=[mock_template])
        mock_feature.handle_tool_call.return_value = json.dumps({"ok": True})
        mock_feature.handle_resource_request.return_value = json.dumps({"build_id": "456"})

        with patch.object(server, "load_features", return_value=[mock_feature]):
            await server.setup()

        ctx = MagicMock()

        tools_res = await server.server.get_request_handler("tools/list").handler(
            ctx, PaginatedRequestParams()
        )
        assert len(tools_res.tools) == 1
        assert tools_res.tools[0].name == "test.tool"

        call_res = await server.server.get_request_handler("tools/call").handler(
            ctx, CallToolRequestParams(name="test.tool", arguments={"k": "v"})
        )
        assert isinstance(call_res.content[0], TextContent)
        assert json.loads(call_res.content[0].text) == {"ok": True}

        resources_res = await server.server.get_request_handler("resources/list").handler(
            ctx, PaginatedRequestParams()
        )
        assert len(resources_res.resources) == 1

        templates_res = await server.server.get_request_handler(
            "resources/templates/list"
        ).handler(ctx, PaginatedRequestParams())
        assert len(templates_res.resource_templates) == 1
        assert templates_res.resource_templates[0].uri_template == "changes://build/{build_id}"

        read_static = await server.server.get_request_handler("resources/read").handler(
            ctx, ReadResourceRequestParams(uri="test://resource")
        )
        assert json.loads(read_static.contents[0].text) == {"build_id": "456"}

        read_template = await server.server.get_request_handler("resources/read").handler(
            ctx, ReadResourceRequestParams(uri="changes://build/456")
        )
        assert json.loads(read_template.contents[0].text) == {"build_id": "456"}
        mock_feature.handle_resource_request.assert_called_with("changes://build/456")

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_unknown_and_error(self, server):
        """Test tool dispatch for unknown tool and handler exception"""
        unknown = await server.dispatch_tool_call("missing.tool", {})
        assert unknown.is_error is True
        assert json.loads(unknown.content[0].text) == {"error": "Unknown tool: missing.tool"}

        mock_feature = AsyncMock()
        mock_feature.handle_tool_call.side_effect = RuntimeError("Tool boom")
        server.tool_handlers = {"failing.tool": mock_feature}

        errored = await server.dispatch_tool_call("failing.tool", {})
        assert errored.is_error is True
        assert json.loads(errored.content[0].text) == {"error": "Tool boom"}

    @pytest.mark.asyncio
    async def test_dispatch_resource_request_unknown_and_error(self, server):
        """Test resource dispatch for unknown URI and handler exception"""
        unknown = await server.dispatch_resource_request("unknown://resource")
        assert unknown == "Unknown resource: unknown://resource"

        mock_feature = AsyncMock()
        mock_feature.handle_resource_request.side_effect = RuntimeError("Resource boom")
        server.resource_handlers = {"failing://resource": mock_feature}

        errored = await server.dispatch_resource_request("failing://resource")
        assert errored == "Error: Resource boom"

    @pytest.mark.asyncio
    async def test_run_success(self, server):
        """Test successful server run passes initialization options"""
        with patch.object(server, "setup") as mock_setup:
            with patch.object(server.qb_client, "authenticate") as mock_auth:
                with patch.object(server.qb_client, "close") as mock_close:
                    with patch("src.server.stdio_server") as mock_stdio:
                        mock_stdio.return_value.__aenter__.return_value = (
                            MagicMock(),
                            MagicMock(),
                        )
                        with patch.object(server.server, "run") as mock_run:
                            await server.run()

                            mock_setup.assert_called_once()
                            mock_auth.assert_called_once()
                            mock_run.assert_called_once()
                            assert len(mock_run.call_args.args) == 3
                            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_setup_error(self, server):
        """Test server run with setup error"""
        with patch.object(server, "setup", side_effect=Exception("Setup failed")):
            with patch.object(server.qb_client, "close") as mock_close:
                with pytest.raises(Exception, match="Setup failed"):
                    await server.run()

                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_auth_error(self, server):
        """Test server run with authentication error"""
        with patch.object(server, "setup"):
            with patch.object(
                server.qb_client, "authenticate", side_effect=Exception("Auth failed")
            ):
                with patch.object(server.qb_client, "close") as mock_close:
                    with pytest.raises(Exception, match="Auth failed"):
                        await server.run()

                    mock_close.assert_called_once()


class TestServerMain:
    """Test server main function"""

    @pytest.mark.asyncio
    async def test_main_function(self):
        """Test main function creates and runs server"""
        with patch("src.server.QuickBuildMCPServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server

            from src.server import main

            await main()

            mock_server_class.assert_called_once()
            mock_server.run.assert_called_once()
