import json
import logging
from typing import Any, List

from mcp.types import Resource, ResourceTemplate, Tool

from ..base import Feature
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)


class ChangesFeature(Feature):
    """Feature for accessing SCM changes for builds"""

    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client

    def get_tools(self) -> List[Tool]:
        """Return list of tools provided by changes feature"""
        return []

    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by changes feature"""
        return [
            Resource(
                uri="changes://build/{build_id}",
                name="Build Changes",
                description="Get SCM changes for a specific build",
                mime_type="application/json",
            )
        ]

    def get_resource_templates(self) -> List[ResourceTemplate]:
        """Return list of resource templates provided by changes feature"""
        return [
            ResourceTemplate(
                uri_template="changes://build/{build_id}",
                name="Build Changes",
                description="Get SCM changes for a specific build",
                mime_type="application/json",
            )
        ]

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for changes feature"""
        raise NotImplementedError(f"Tool {name} not implemented")

    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for changes feature"""
        if uri.startswith("changes://build/"):
            build_id = uri.removeprefix("changes://build/").strip()
            if not build_id or build_id == "{build_id}":
                return json.dumps({"error": "build_id is required"})
            return await self._get_build_changes(build_id)
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    async def _get_build_changes(self, build_id: str) -> str:
        """Get SCM changes for a specific build"""
        try:
            changes = await self.qb_client.get_build_changes(build_id)

            change_data = [
                {
                    "revision": change.revision,
                    "author": change.author,
                    "message": change.message,
                    "timestamp": change.timestamp.isoformat(),
                    "repository": change.repository,
                    "files": change.files,
                    "modifications": change.modifications,
                }
                for change in changes
            ]

            result = {
                "build_id": build_id,
                "changes": change_data,
                "count": len(change_data),
            }

            logger.info(f"Retrieved {len(change_data)} changes for build {build_id}")
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error getting changes for build {build_id}: {e}")
            return json.dumps({"error": str(e)})
