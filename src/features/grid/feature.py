import json
import logging
from typing import Any, List

from mcp.types import Resource, Tool

from ..base import Feature, error_json, read_only_tool
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
                annotations=read_only_tool("Build agents"),
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="grid.list_unauthorized",
                description=(
                    "List build agents that have contacted the server but are not authorized "
                    "yet (QuickBuild 16 agents must be authorized before they take builds)"
                ),
                annotations=read_only_tool("Unauthorized agents"),
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
        ]

    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by grid feature"""
        return []

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for grid feature"""
        if name == "grid.list_agents":
            return await self._list_agents()
        elif name == "grid.list_unauthorized":
            return await self._list_unauthorized()
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for grid feature"""
        raise ValueError(f"Unknown resource URI: {uri}")

    async def _list_agents(self) -> str:
        """List all build agents and their status"""
        try:
            agents = await self.qb_client.get_agents()

            agent_data = [
                {
                    "name": agent.name,
                    "status": agent.status,
                    "last_contact": agent.last_contact.isoformat(),
                    "ip_address": agent.ip_address,
                    "port": agent.port,
                }
                for agent in agents
            ]

            result = {
                "agents": agent_data,
                "count": len(agent_data),
                "online_count": len([a for a in agents if a.status.lower() == "online"]),
                "offline_count": len([a for a in agents if a.status.lower() == "offline"]),
            }

            logger.info(f"Listed {len(agent_data)} agents")
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return json.dumps({"error": str(e)})

    async def _list_unauthorized(self) -> str:
        try:
            agents = await self.qb_client.get_unauthorized_agents()
            data = [
                {
                    "name": agent.name,
                    "ip_address": agent.ip_address,
                    "port": agent.port,
                    "last_contact": agent.last_contact.isoformat(),
                }
                for agent in agents
            ]
            result = {
                "agents": data,
                "count": len(data),
                "note": "An administrator authorizes these on the Grid page (Unauthorized Nodes).",
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error listing unauthorized agents: {e}")
            return error_json(str(e))
