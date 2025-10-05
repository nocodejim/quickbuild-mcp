import json
import logging
from typing import List, Any

from mcp.types import Tool, Resource

from ..base import Feature
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)

class GridFeature(Feature):
    """Feature for managing QuickBuild build agent grid"""
    
    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client
    
    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by grid feature"""
        return [
            Tool(
                name="grid.list_agents",
                description="List all build agents and their connection status",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            )
        ]
    
    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by grid feature"""
        return []  # No resources for grid in MVP
    
    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for grid feature"""
        if name == "grid.list_agents":
            return await self._list_agents()
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for grid feature"""
        # No resources implemented in MVP
        raise ValueError(f"Unknown resource URI: {uri}")
    
    async def _list_agents(self) -> str:
        """List all build agents and their status"""
        try:
            agents = await self.qb_client.get_agents()
            
            # Convert to JSON-serializable format
            agent_data = []
            for agent in agents:
                agent_data.append({
                    "name": agent.name,
                    "status": agent.status,
                    "last_contact": agent.last_contact.isoformat(),
                    "ip_address": agent.ip_address,
                    "port": agent.port
                })
            
            result = {
                "agents": agent_data,
                "count": len(agent_data),
                "online_count": len([a for a in agents if a.status.lower() == "online"]),
                "offline_count": len([a for a in agents if a.status.lower() == "offline"])
            }
            
            logger.info(f"Listed {len(agent_data)} agents")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return json.dumps({"error": str(e)})