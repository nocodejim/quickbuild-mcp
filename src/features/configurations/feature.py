import json
import logging
from typing import List, Any

from mcp.types import Tool, Resource

from ..base import Feature
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)

class ConfigurationsFeature(Feature):
    """Feature for managing QuickBuild configurations"""
    
    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client
    
    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by configurations feature"""
        return []  # No tools for configurations in MVP
    
    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by configurations feature"""
        return [
            Resource(
                uri="configurations://list",
                name="Build Configurations",
                description="List all available build configurations in QuickBuild",
                mimeType="application/json"
            )
        ]
    
    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for configurations feature"""
        # No tools implemented in MVP
        raise NotImplementedError(f"Tool {name} not implemented")
    
    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for configurations feature"""
        if uri == "configurations://list":
            return await self._list_configurations()
        else:
            raise ValueError(f"Unknown resource URI: {uri}")
    
    async def _list_configurations(self) -> str:
        """List all build configurations"""
        try:
            configurations = await self.qb_client.get_configurations()
            
            # Convert to JSON-serializable format
            config_data = []
            for config in configurations:
                config_data.append({
                    "id": config.id,
                    "name": config.name,
                    "description": config.description,
                    "parent_id": config.parent_id,
                    "enabled": config.enabled
                })
            
            result = {
                "configurations": config_data,
                "count": len(config_data)
            }
            
            logger.info(f"Listed {len(config_data)} configurations")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error listing configurations: {e}")
            return json.dumps({"error": str(e)}, indent=2)