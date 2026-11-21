import json
import logging
from typing import Any, List

from mcp.types import Resource, Tool

from ..base import Feature, bounded_int, error_json, read_only_tool
from ...models import Configuration
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)


def _config_dict(config: Configuration) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "path": config.path,
        "description": config.description,
        "parent_id": config.parent_id,
        "enabled": config.enabled,
    }


def _match_rank(config: Configuration, needle: str) -> int:
    """0 = best match; -1 = no match. Case-insensitive."""
    name, path = config.name.lower(), config.path.lower()
    if needle == config.id or needle == name or needle == path:
        return 0
    if name.startswith(needle):
        return 1
    if needle in name:
        return 2
    if needle in path:
        return 3
    if needle in (config.description or "").lower():
        return 4
    return -1


class ConfigurationsFeature(Feature):
    """Feature for managing QuickBuild configurations"""

    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client

    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by configurations feature"""
        return [
            Tool(
                name="configurations.search",
                description=(
                    "Find build configurations by id, name, path (e.g. root/team/app) or "
                    "description text; case-insensitive, best matches first"
                ),
                annotations=read_only_tool("Search configurations"),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to look for in configuration ids, names, paths and descriptions",
                            "minLength": 1,
                        },
                        "include_disabled": {
                            "type": "boolean",
                            "description": "Include disabled configurations (default true)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 25, max 200)",
                            "minimum": 1,
                            "maximum": 200,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
        ]

    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by configurations feature"""
        return [
            Resource(
                uri="configurations://list",
                name="Build Configurations",
                description="List all available build configurations in QuickBuild",
                mime_type="application/json",
            )
        ]

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for configurations feature"""
        if name == "configurations.search":
            return await self._search(arguments)
        raise ValueError(f"Unknown tool: {name}")

    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for configurations feature"""
        if uri == "configurations://list":
            return await self._list_configurations()
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    async def _search(self, arguments: dict) -> str:
        try:
            query = str(arguments.get("query") or "").strip()
            if not query:
                return error_json("query is required")
            include_disabled = arguments.get("include_disabled", True) is not False
            limit = bounded_int(arguments, "limit", 25, 1, 200)

            needle = query.lower()
            ranked = []
            for config in await self.qb_client.get_configurations():
                if not include_disabled and not config.enabled:
                    continue
                rank = _match_rank(config, needle)
                if rank >= 0:
                    ranked.append((rank, config.path or config.name, config))
            ranked.sort(key=lambda item: (item[0], item[1]))

            matches = [_config_dict(config) for _, _, config in ranked[:limit]]
            result = {
                "query": query,
                "configurations": matches,
                "count": len(matches),
                "total_matches": len(ranked),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error searching configurations: {e}")
            return error_json(str(e))

    async def _list_configurations(self) -> str:
        """List all build configurations"""
        try:
            configurations = await self.qb_client.get_configurations()

            config_data = [_config_dict(config) for config in configurations]

            result = {
                "configurations": config_data,
                "count": len(config_data),
            }

            logger.info(f"Listed {len(config_data)} configurations")
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error listing configurations: {e}")
            return json.dumps({"error": str(e)}, indent=2)
