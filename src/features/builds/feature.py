import json
import logging
from typing import Any, List

from mcp.types import Resource, Tool

from ..base import Feature, bounded_int, error_json, read_only_tool, write_tool
from ...models import Build
from ...quickbuild_client import MAX_LOG_TAIL_LINES, QuickBuildClient

logger = logging.getLogger(__name__)

_BUILD_ID = {"type": "string", "description": "The numeric QuickBuild build id"}


def _build_summary(build: Build) -> dict:
    return {
        "build_id": build.id,
        "configuration_id": build.configuration_id,
        "version": build.version,
        "status": build.status,
        "start_time": build.start_time.isoformat(),
        "node": build.node,
        "requester_id": build.requester_id,
    }


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
                annotations=read_only_tool("Latest build status"),
                input_schema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "The build configuration: numeric id or path (e.g. root/team/app)",
                        }
                    },
                    "required": ["configuration_id"],
                },
            ),
            Tool(
                name="builds.get",
                description=(
                    "Get one build: status, version, timing, the node it ran on, each step's "
                    "status and duration, checked-out repository revisions and request variables"
                ),
                annotations=read_only_tool("Get build"),
                input_schema={
                    "type": "object",
                    "properties": {"build_id": _BUILD_ID},
                    "required": ["build_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="builds.get_log",
                description=(
                    "Get the last lines of a finished build's log (QuickBuild serves the log "
                    "once the build has finished)"
                ),
                annotations=read_only_tool("Build log tail"),
                input_schema={
                    "type": "object",
                    "properties": {
                        "build_id": _BUILD_ID,
                        "tail_lines": {
                            "type": "integer",
                            "description": f"Number of lines from the end (default 200, max {MAX_LOG_TAIL_LINES})",
                            "minimum": 1,
                            "maximum": MAX_LOG_TAIL_LINES,
                        },
                    },
                    "required": ["build_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="builds.list_running",
                description="List builds that are currently running",
                annotations=read_only_tool("Running builds"),
                input_schema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "Optional configuration id or path (e.g. root/team); includes its child configurations",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of builds (default 20, max 100)",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="builds.trigger",
                description="Trigger a new build for a configuration",
                annotations=write_tool("Trigger build", destructive=False, idempotent=False),
                input_schema={
                    "type": "object",
                    "properties": {
                        "configuration_id": {
                            "type": "string",
                            "description": "The build configuration to trigger: numeric id or path (e.g. root/team/app)",
                        },
                        "variables": {
                            "type": "object",
                            "description": "Optional build variables as key-value pairs",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["configuration_id"],
                },
            ),
        ]

    def get_resources(self) -> List[Resource]:
        """Return list of resources provided by builds feature"""
        return []

    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool calls for builds feature"""
        if name == "builds.get_latest_status":
            return await self._get_latest_status(arguments)
        elif name == "builds.get":
            return await self._get_build(arguments)
        elif name == "builds.get_log":
            return await self._get_log(arguments)
        elif name == "builds.list_running":
            return await self._list_running(arguments)
        elif name == "builds.trigger":
            return await self._trigger_build(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource requests for builds feature"""
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
                    "message": "No builds found for this configuration",
                }
            else:
                result = {
                    "configuration_id": config_id,
                    "build_id": build.id,
                    "version": build.version,
                    "status": build.status,
                    "start_time": build.start_time.isoformat(),
                    "end_time": build.end_time.isoformat() if build.end_time else None,
                    "success": build.success,
                }

            logger.info(f"Retrieved build status for configuration {config_id}")
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error getting build status: {e}")
            return json.dumps({"error": str(e)})

    async def _get_build(self, arguments: dict) -> str:
        try:
            build_id = arguments.get("build_id")
            if not build_id:
                return error_json("build_id is required")
            build = await self.qb_client.get_build(build_id)
            result = {
                **_build_summary(build),
                "success": build.success,
                "end_time": build.end_time.isoformat() if build.end_time else None,
                "duration_ms": build.duration_ms,
                "wait_duration_ms": build.wait_duration_ms,
                "scheduled": build.scheduled,
                "steps": build.steps,
                "revisions": build.revisions,
                "variables": build.variables,
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting build: {e}")
            return error_json(str(e))

    async def _get_log(self, arguments: dict) -> str:
        try:
            build_id = arguments.get("build_id")
            if not build_id:
                return error_json("build_id is required")
            tail_lines = bounded_int(arguments, "tail_lines", 200, 1, MAX_LOG_TAIL_LINES)
            log = await self.qb_client.get_build_log(build_id, tail_lines=tail_lines)
            result = {
                "build_id": log["build_id"],
                "line_count": log["line_count"],
                "log_bytes": log["log_bytes"],
                "truncated": log["truncated"],
                "log": "\n".join(log["lines"]),
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting build log: {e}")
            return error_json(str(e))

    async def _list_running(self, arguments: dict) -> str:
        try:
            limit = bounded_int(arguments, "limit", 20, 1, 100)
            builds = await self.qb_client.search_builds(
                status="RUNNING",
                configuration_id=arguments.get("configuration_id") or None,
                count=limit,
            )
            running = [_build_summary(b) for b in builds]
            return json.dumps({"builds": running, "count": len(running)}, indent=2)
        except Exception as e:
            logger.error(f"Error listing running builds: {e}")
            return error_json(str(e))

    async def _trigger_build(self, arguments: dict) -> str:
        """Trigger a new build"""
        try:
            config_id = arguments.get("configuration_id")
            variables = arguments.get("variables", {})

            if not config_id:
                return json.dumps({"error": "configuration_id is required"})

            result = await self.qb_client.trigger_build(config_id, variables)

            logger.info(f"Triggered build for configuration {config_id}")
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error triggering build: {e}")
            return json.dumps({"error": str(e)})
