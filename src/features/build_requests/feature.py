import json
import logging
from typing import Any, List

from mcp.types import Resource, Tool

from ..base import Feature, error_json, read_only_tool, write_tool
from ...quickbuild_client import QuickBuildClient

logger = logging.getLogger(__name__)


class BuildRequestsFeature(Feature):
    """Feature for the QuickBuild build queue (build requests)"""

    def __init__(self, qb_client: QuickBuildClient):
        self.qb_client = qb_client

    def get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="build_requests.list",
                description=(
                    "List the build queue: requests waiting to be processed (WAITING_PROCESS) "
                    "and requests whose build is running (RUNNING_BUILD)"
                ),
                annotations=read_only_tool("Build queue"),
                input_schema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "Optional configuration id or path (e.g. root/team/app) to filter by",
                        }
                    },
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="build_requests.cancel",
                description=(
                    "Cancel a build request by its request id (as returned by builds.trigger or "
                    "build_requests.list); a running build is stopped and ends as CANCELLED"
                ),
                annotations=write_tool("Cancel build request", destructive=True, idempotent=True),
                input_schema={
                    "type": "object",
                    "properties": {
                        "request_id": {
                            "type": "string",
                            "description": "The build request id (a UUID)",
                        }
                    },
                    "required": ["request_id"],
                    "additionalProperties": False,
                },
            ),
        ]

    def get_resources(self) -> List[Resource]:
        return []

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        if name == "build_requests.list":
            return await self._list(arguments)
        elif name == "build_requests.cancel":
            return await self._cancel(arguments)
        raise ValueError(f"Unknown tool: {name}")

    async def handle_resource_request(self, uri: str) -> Any:
        raise ValueError(f"Unknown resource URI: {uri}")

    async def _list(self, arguments: dict) -> str:
        try:
            requests = await self.qb_client.get_build_requests(
                arguments.get("configuration_id") or None
            )
            data = [
                {
                    "request_id": r.id,
                    "configuration_id": r.configuration_id,
                    "status": r.status,
                    "requested_at": r.requested_at.isoformat(),
                    "requester_id": r.requester_id,
                    "priority": r.priority,
                    "scheduled": r.scheduled,
                    "variables": r.variables,
                }
                for r in requests
            ]
            result = {
                "requests": data,
                "count": len(data),
                "waiting_count": len([r for r in requests if r.status == "WAITING_PROCESS"]),
                "running_count": len([r for r in requests if r.status == "RUNNING_BUILD"]),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error listing build requests: {e}")
            return error_json(str(e))

    async def _cancel(self, arguments: dict) -> str:
        try:
            request_id = arguments.get("request_id")
            if not request_id:
                return error_json("request_id is required")
            result = await self.qb_client.cancel_build_request(request_id)
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error cancelling build request: {e}")
            return error_json(str(e))
