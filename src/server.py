import asyncio
import logging
import os
from typing import List, Dict, Any

from mcp.server import Server
from mcp.types import Tool, Resource, TextContent
from mcp.server.stdio import stdio_server

from .quickbuild_client import QuickBuildClient
from .features.base import Feature
from .features.configurations.feature import ConfigurationsFeature
from .features.builds.feature import BuildsFeature
from .features.grid.feature import GridFeature
from .features.changes.feature import ChangesFeature

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class QuickBuildMCPServer:
    """Main MCP server for QuickBuild integration"""
    
    def __init__(self):
        self.server = Server("quickbuild-mcp-server")
        self.qb_client = QuickBuildClient()
        self.features: List[Feature] = []
        self.tool_handlers: Dict[str, Feature] = {}
        self.resource_handlers: Dict[str, Feature] = {}
        
    def load_features(self) -> List[Feature]:
        """Load and initialize all feature modules"""
        features = [
            ConfigurationsFeature(self.qb_client),
            BuildsFeature(self.qb_client),
            GridFeature(self.qb_client),
            ChangesFeature(self.qb_client),
        ]
        
        logger.info(f"Loaded {len(features)} features")
        return features
    
    async def setup(self):
        """Initialize server and register features"""
        try:
            # Load features
            self.features = self.load_features()
            
            # Register tools and resources
            all_tools = []
            all_resources = []
            
            for feature in self.features:
                # Get tools and resources from each feature
                tools = feature.get_tools()
                resources = feature.get_resources()
                
                all_tools.extend(tools)
                all_resources.extend(resources)
                
                # Map tool names to feature handlers
                for tool in tools:
                    self.tool_handlers[tool.name] = feature
                
                # Map resource URIs to feature handlers  
                for resource in resources:
                    self.resource_handlers[resource.uri] = feature
            
            # Register tool handler
            @self.server.call_tool()
            async def handle_tool_call(name: str, arguments: dict) -> List[TextContent]:
                try:
                    if name in self.tool_handlers:
                        result = await self.tool_handlers[name].handle_tool_call(name, arguments)
                        return [TextContent(type="text", text=str(result))]
                    else:
                        return [TextContent(type="text", text=f"Unknown tool: {name}")]
                except Exception as e:
                    logger.error(f"Error handling tool call {name}: {e}")
                    return [TextContent(type="text", text=f"Error: {str(e)}")]
            
            # Register resource handler
            @self.server.read_resource()
            async def handle_resource_request(uri: str) -> str:
                try:
                    if uri in self.resource_handlers:
                        result = await self.resource_handlers[uri].handle_resource_request(uri)
                        return str(result)
                    else:
                        return f"Unknown resource: {uri}"
                except Exception as e:
                    logger.error(f"Error handling resource request {uri}: {e}")
                    return f"Error: {str(e)}"
            
            # List available tools
            @self.server.list_tools()
            async def list_tools() -> List[Tool]:
                return all_tools
            
            # List available resources
            @self.server.list_resources()
            async def list_resources() -> List[Resource]:
                return all_resources
            
            logger.info(f"Server setup complete - {len(all_tools)} tools, {len(all_resources)} resources")
            
        except Exception as e:
            logger.error(f"Error during server setup: {e}")
            raise
    
    async def run(self):
        """Run the MCP server"""
        try:
            await self.setup()
            
            # Test QuickBuild connection
            await self.qb_client.authenticate()
            logger.info("QuickBuild connection verified")
            
            # Run the server
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(read_stream, write_stream)
                
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            await self.qb_client.close()

async def main():
    """Main entry point"""
    server = QuickBuildMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())