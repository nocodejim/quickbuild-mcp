import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    ResourceTemplate,
    TextContent,
    TextResourceContents,
    Tool,
)

from .features.base import Feature
from .features.builds.feature import BuildsFeature
from .features.changes.feature import ChangesFeature
from .features.configurations.feature import ConfigurationsFeature
from .features.grid.feature import GridFeature
from .features.system.feature import SystemFeature
from .quickbuild_client import QuickBuildClient

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class QuickBuildMCPServer:
    """Main MCP server for QuickBuild integration"""

    def __init__(self):
        self.server = Server("quickbuild-mcp-server", version="0.2.0")
        self.qb_client = QuickBuildClient()
        self.features: List[Feature] = []
        self.tool_handlers: Dict[str, Feature] = {}
        self.resource_handlers: Dict[str, Feature] = {}
        self.resource_template_handlers: List[Tuple[str, Feature]] = []

    def load_features(self) -> List[Feature]:
        """Load and initialize all feature modules"""
        features: List[Feature] = [
            ConfigurationsFeature(self.qb_client),
            BuildsFeature(self.qb_client),
            GridFeature(self.qb_client),
            ChangesFeature(self.qb_client),
            SystemFeature(self.qb_client),
        ]

        logger.info(f"Loaded {len(features)} features")
        return features

    def _register_template_handler(self, uri_template: str, feature: Feature) -> None:
        """Register a prefix handler for parameterized URI templates like changes://build/{build_id}."""
        prefix = uri_template.split("{", 1)[0]
        if prefix and all(existing != (prefix, feature) for existing in self.resource_template_handlers):
            self.resource_template_handlers.append((prefix, feature))

    async def dispatch_tool_call(
        self, name: str, arguments: Optional[dict] = None
    ) -> List[TextContent]:
        """Dispatch an MCP tool call to the matching feature handler."""
        try:
            if name in self.tool_handlers:
                result = await self.tool_handlers[name].handle_tool_call(name, arguments or {})
                return [TextContent(type="text", text=str(result))]
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Error handling tool call {name}: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def dispatch_resource_request(self, uri: str) -> str:
        """Dispatch an MCP resource read request to the matching feature handler."""
        uri_str = str(uri)
        try:
            if uri_str in self.resource_handlers:
                result = await self.resource_handlers[uri_str].handle_resource_request(uri_str)
                return str(result)

            for prefix, feature in self.resource_template_handlers:
                if uri_str.startswith(prefix):
                    result = await feature.handle_resource_request(uri_str)
                    return str(result)

            return f"Unknown resource: {uri_str}"
        except Exception as e:
            logger.error(f"Error handling resource request {uri_str}: {e}")
            return f"Error: {str(e)}"

    async def setup(self) -> None:
        """Initialize server and register features"""
        try:
            self.features = self.load_features()
            self.tool_handlers.clear()
            self.resource_handlers.clear()
            self.resource_template_handlers.clear()

            all_tools: List[Tool] = []
            all_resources: List[Resource] = []
            all_resource_templates: List[ResourceTemplate] = []

            for feature in self.features:
                tools = feature.get_tools()
                resources = feature.get_resources()
                templates = (
                    feature.get_resource_templates()
                    if hasattr(feature, "get_resource_templates")
                    else []
                )

                all_tools.extend(tools)
                all_resources.extend(resources)
                if isinstance(templates, list):
                    all_resource_templates.extend(templates)
                    for template in templates:
                        self._register_template_handler(str(template.uri_template), feature)

                for tool in tools:
                    self.tool_handlers[tool.name] = feature

                for resource in resources:
                    uri_str = str(resource.uri)
                    self.resource_handlers[uri_str] = feature
                    if "{" in uri_str:
                        self._register_template_handler(uri_str, feature)

            async def handle_list_tools(
                ctx: Any, params: Optional[PaginatedRequestParams]
            ) -> ListToolsResult:
                return ListToolsResult(tools=all_tools)

            async def handle_call_tool(
                ctx: Any, params: CallToolRequestParams
            ) -> CallToolResult:
                content = await self.dispatch_tool_call(params.name, params.arguments or {})
                return CallToolResult(content=content)

            async def handle_list_resources(
                ctx: Any, params: Optional[PaginatedRequestParams]
            ) -> ListResourcesResult:
                return ListResourcesResult(resources=all_resources)

            async def handle_list_resource_templates(
                ctx: Any, params: Optional[PaginatedRequestParams]
            ) -> ListResourceTemplatesResult:
                return ListResourceTemplatesResult(resource_templates=all_resource_templates)

            async def handle_read_resource(
                ctx: Any, params: ReadResourceRequestParams
            ) -> ReadResourceResult:
                uri_str = str(params.uri)
                text = await self.dispatch_resource_request(uri_str)
                return ReadResourceResult(
                    contents=[
                        TextResourceContents(
                            uri=uri_str,
                            text=text,
                            mime_type="application/json",
                        )
                    ]
                )

            self.server.add_request_handler("tools/list", PaginatedRequestParams, handle_list_tools)
            self.server.add_request_handler("tools/call", CallToolRequestParams, handle_call_tool)
            self.server.add_request_handler(
                "resources/list", PaginatedRequestParams, handle_list_resources
            )
            self.server.add_request_handler(
                "resources/templates/list",
                PaginatedRequestParams,
                handle_list_resource_templates,
            )
            self.server.add_request_handler(
                "resources/read", ReadResourceRequestParams, handle_read_resource
            )

            logger.info(
                f"Server setup complete - {len(all_tools)} tools, "
                f"{len(all_resources)} resources, {len(all_resource_templates)} resource templates"
            )

        except Exception as e:
            logger.error(f"Error during server setup: {e}")
            raise

    async def run(self) -> None:
        """Run the MCP server"""
        try:
            await self.setup()

            await self.qb_client.authenticate()
            logger.info("QuickBuild connection verified")

            async with stdio_server() as (read_stream, write_stream):
                init_options = self.server.create_initialization_options()
                await self.server.run(read_stream, write_stream, init_options)

        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            await self.qb_client.close()


async def main() -> None:
    """Main entry point"""
    server = QuickBuildMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
