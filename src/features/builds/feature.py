import json
import logging
from typing import List, Any

from mcp.types import Tool, Resource

from ..base import Feature
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)

class BuildsFeature(Feature):
    """Feature for managing QuickBuild builds"""
    
    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client
    
    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by builds feature"""
        return [
            Tool(
                name="builds.get_latest_status",
                description="Get the status of the latest build for a configuration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "The ID of the build configuration"
                        }
                    },
                    "required": ["configuration_id"]
                }
            ),
            Tool(
                name="builds.trigger",
                description="Trigger a new build for a configuration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "The ID of the build configuration to trigger"
                        },
                        "variables": {
                            "type": "object",
                            "description": "Optional build variables as key-value pairs",
                            "additionalProperties": {"type": "string"}
                        }
                    },
                    "required": ["configuration_id"]
                }
            )
        ]
    
    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by builds feature"""
        return []  # No resources for builds in MVP
    
    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for builds feature"""
        if name == "builds.get_latest_status":
            return await self._get_latest_status(arguments)
        elif name == "builds.trigger":
            return await self._trigger_build(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for builds feature"""
        # No resources implemented in MVP
        raise ValueError(f"Unknown resource URI: {uri}")
    
    async def _get_latest_status(self, arguments: dict) -> str:
        """Get latest build status for a configuration"""
        try:
            config_id = arguments.get("configuration_id")
            if not config_id:
                return json.dumps({"error": "configuration_id is required"})
            
            build = await self.qb_client.get_latest_build_status(config_id)
            
            if build is None:
                result = {
                    "configuration_id": config_id,
                    "message": "No builds found for this configuration"
                }
            else:
                result = {
                    "configuration_id": config_id,
                    "build_id": build.id,
                    "version": build.version,
                    "status": build.status,
                    "start_time": build.start_time.isoformat(),
                    "end_time": build.end_time.isoformat() if build.end_time else None,
                    "success": build.success
                }
            
            logger.info(f"Retrieved build status for configuration {config_id}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting build status: {e}")
            return json.dumps({"error": str(e)})
    
    async def _trigger_build(self, arguments: dict) -> str:
        """Trigger a new build"""
        try:
            config_id = arguments.get("configuration_id")
            variables = arguments.get("variables", {})
            
            if not config_id:
                return json.dumps({"error": "configuration_id is required"})
            
            # Add trigger_build method to QuickBuildClient
            result = await self.qb_client.trigger_build(config_id, variables)
            
            logger.info(f"Triggered build for configuration {config_id}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error triggering build: {e}")
            return json.dumps({"error": str(e)})