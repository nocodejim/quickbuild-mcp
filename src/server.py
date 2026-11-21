import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
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

from . import __version__
from .config import Settings
from .features.base import Feature, is_write_tool
from .features.build_requests.feature import BuildRequestsFeature
from .features.builds.feature import BuildsFeature
from .features.changes.feature import ChangesFeature
from .features.configurations.feature import ConfigurationsFeature
from .features.grid.feature import GridFeature
from .features.system.feature import SystemFeature
from .quickbuild_client import QuickBuildClient

load_dotenv()

# Configure logging (stderr: stdout carries the MCP stdio protocol)
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SERVER_NAME = "quickbuild-mcp-server"
READY_TIMEOUT_SECONDS = 5.0


def _is_error_payload(text: str) -> bool:
    """Feature handlers report failures as a JSON object with an "error" key."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and "error" in payload


def _error_result(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"error": message}))],
        is_error=True,
    )


class QuickBuildMCPServer:
    """Main MCP server for QuickBuild integration"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()
        self.server = Server(SERVER_NAME, version=__version__)
        self.qb_client = QuickBuildClient(settings=self.settings)
        self.read_only = self.settings.read_only
        self.features: List[Feature] = []
        self.tool_handlers: Dict[str, Feature] = {}
        self.resource_handlers: Dict[str, Feature] = {}
        self.resource_template_handlers: List[Tuple[str, Feature]] = []
        # Write tools refused (and hidden from tools/list) because QB_READ_ONLY=true
        self.disabled_tools: Set[str] = set()
        self.tools: List[Tool] = []

    def load_features(self) -> List[Feature]:
        """Load and initialize all feature modules"""
        features: List[Feature] = [
            ConfigurationsFeature(self.qb_client),
            BuildsFeature(self.qb_client),
            BuildRequestsFeature(self.qb_client),
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
    ) -> CallToolResult:
        """Dispatch an MCP tool call to the matching feature handler.

        Failures are returned with isError=true so clients and gateways can tell them apart
        from results. Write tools are refused in read-only mode even when called by name.
        """
        if name in self.disabled_tools:
            logger.warning(f"Refused write tool {name}: QB_READ_ONLY=true")
            return _error_result(
                f"Tool '{name}' is disabled: this server runs read-only (QB_READ_ONLY=true)"
            )
        if name not in self.tool_handlers:
            return _error_result(f"Unknown tool: {name}")
        try:
            result = await self.tool_handlers[name].handle_tool_call(name, arguments or {})
            text = str(result)
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                is_error=_is_error_payload(text),
            )
        except Exception as e:
            logger.error(f"Error handling tool call {name}: {e}")
            return _error_result(str(e))

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
            self.disabled_tools.clear()

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

            if self.read_only:
                self.disabled_tools = {t.name for t in all_tools if is_write_tool(t)}
                all_tools = [t for t in all_tools if t.name not in self.disabled_tools]
                logger.info(
                    "Read-only mode (QB_READ_ONLY=true): write tools hidden and refused: "
                    + ", ".join(sorted(self.disabled_tools))
                )
            self.tools = all_tools

            async def handle_list_tools(
                ctx: Any, params: Optional[PaginatedRequestParams]
            ) -> ListToolsResult:
                return ListToolsResult(tools=all_tools)

            async def handle_call_tool(
                ctx: Any, params: CallToolRequestParams
            ) -> CallToolResult:
                return await self.dispatch_tool_call(params.name, params.arguments or {})

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

    # ------------------------------------------------------------------ HTTP transport

    def health_payload(self) -> dict:
        return {
            "status": "ok",
            "server": SERVER_NAME,
            "version": __version__,
            "transport": self.settings.transport,
            "read_only": self.read_only,
        }

    async def readiness(self) -> Tuple[int, dict]:
        """(HTTP status, body) for /ready: 200 when QuickBuild answers /rest/version in time."""
        try:
            version = await asyncio.wait_for(
                self.qb_client.get_version(), timeout=READY_TIMEOUT_SECONDS
            )
            return 200, {"status": "ready", "quickbuild_version": version.get("version")}
        except asyncio.TimeoutError:
            return 503, {
                "status": "unavailable",
                "error": f"QuickBuild did not answer within {READY_TIMEOUT_SECONDS:g}s",
            }
        except Exception as e:
            return 503, {"status": "unavailable", "error": str(e)}

    def transport_security(self) -> Optional[TransportSecuritySettings]:
        """DNS rebinding protection settings for the HTTP transport.

        With MCP_ALLOWED_HOSTS set, Host (and Origin, when sent) headers are checked against the
        lists. Without it the SDK protects loopback binds itself; a non-loopback bind (e.g. 0.0.0.0
        in a container behind a gateway) then accepts any Host header.
        """
        if self.settings.allowed_hosts:
            return TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(self.settings.allowed_hosts),
                allowed_origins=list(self.settings.allowed_origins),
            )
        if self.settings.host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "MCP_HOST=%s without MCP_ALLOWED_HOSTS: Host/Origin headers are not validated "
                "(set MCP_ALLOWED_HOSTS to the names clients use, e.g. the gateway's)",
                self.settings.host,
            )
        return None

    def build_http_app(self):
        """Starlette app: Streamable HTTP MCP endpoint plus /health and /ready."""
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def health(request: Request) -> JSONResponse:
            return JSONResponse(self.health_payload())

        async def ready(request: Request) -> JSONResponse:
            status, body = await self.readiness()
            return JSONResponse(body, status_code=status)

        return self.server.streamable_http_app(
            streamable_http_path=self.settings.http_path,
            stateless_http=self.settings.stateless_http,
            transport_security=self.transport_security(),
            host=self.settings.host,
            custom_starlette_routes=[
                Route("/health", health, methods=["GET"]),
                Route("/ready", ready, methods=["GET"]),
            ],
        )

    async def _serve_http(self) -> None:
        import uvicorn

        app = self.build_http_app()
        config = uvicorn.Config(
            app,
            host=self.settings.host,
            port=self.settings.port,
            log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
            lifespan="on",
        )
        logger.info(
            "Serving MCP over Streamable HTTP on http://%s:%s%s (health: /health, ready: /ready)",
            self.settings.host,
            self.settings.port,
            self.settings.http_path,
        )
        await uvicorn.Server(config).serve()

    async def _serve_stdio(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            init_options = self.server.create_initialization_options()
            await self.server.run(read_stream, write_stream, init_options)

    async def run(self) -> None:
        """Run the MCP server on the transport selected by MCP_TRANSPORT (stdio or http)"""
        try:
            await self.setup()

            await self.qb_client.authenticate()
            logger.info("QuickBuild connection verified")

            if self.settings.transport == "http":
                await self._serve_http()
            else:
                await self._serve_stdio()

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
