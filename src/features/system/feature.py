import json
import logging
from typing import Any, List

from mcp.types import Resource, Tool

from ..base import Feature, read_only_tool, write_tool
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)


class SystemFeature(Feature):
    """Feature for QuickBuild system administration and diagnostics"""

    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client

    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by system feature"""
        return [
            Tool(
                name="system.backup_database",
                description="Initiate a server-side QuickBuild database backup",
                annotations=write_tool("Back up database", destructive=False, idempotent=False),
                input_schema={
                    "type": "object",
                    "properties": {
                        "backup_path": {
                            "type": "string",
                            "description": "Optional target path on the QuickBuild server for the backup file",
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="system.get_version",
                description="Get QuickBuild server version information",
                annotations=read_only_tool("QuickBuild version"),
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
        ]

    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by system feature"""
        return []

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for system feature"""
        if name == "system.backup_database":
            return await self._backup_database(arguments)
        elif name == "system.get_version":
            return await self._get_version()
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for system feature"""
        raise ValueError(f"Unknown resource URI: {uri}")

    async def _backup_database(self, arguments: dict) -> str:
        """Initiate a QuickBuild database backup"""
        try:
            backup_path = arguments.get("backup_path") if arguments else None
            result = await self.qb_client.backup_database(backup_path)
            logger.info("System database backup triggered")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error initiating database backup: {e}")
            return json.dumps({"error": str(e)})

    async def _get_version(self) -> str:
        """Get QuickBuild server version"""
        try:
            result = await self.qb_client.get_version()
            logger.info("Retrieved QuickBuild server version")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting QuickBuild version: {e}")
            return json.dumps({"error": str(e)})
