import json
from abc import ABC, abstractmethod
from typing import Any, List

from mcp.types import Resource, ResourceTemplate, Tool, ToolAnnotations


def read_only_tool(title: str) -> ToolAnnotations:
    """Annotations for a tool that only reads from QuickBuild."""
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def write_tool(title: str, *, destructive: bool, idempotent: bool) -> ToolAnnotations:
    """Annotations for a tool that changes QuickBuild state (hidden when QB_READ_ONLY=true)."""
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=False,
    )


def is_write_tool(tool: Tool) -> bool:
    """A tool is treated as a write tool unless it is explicitly annotated read-only."""
    return not (tool.annotations is not None and tool.annotations.read_only_hint is True)


def error_json(message: str) -> str:
    return json.dumps({"error": message})


def bounded_int(arguments: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    """Read an optional integer argument and clamp it to [minimum, maximum]."""
    value = arguments.get(name, default)
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer (got '{value}')") from None
    return max(minimum, min(number, maximum))


class Feature(ABC):
    """Base class for all feature modules"""

    @abstractmethod
    def get_tools(self) -> List[Tool]:
        """Return list of MCP tools provided by this feature"""
        pass

    @abstractmethod
    def get_resources(self) -> List[Resource]:
        """Return list of MCP resources provided by this feature"""
        pass

    def get_resource_templates(self) -> List[ResourceTemplate]:
        """Return list of MCP resource templates provided by this feature"""
        return []

    @abstractmethod
    async def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle tool call for this feature"""
        pass

    @abstractmethod
    async def handle_resource_request(self, uri: str) -> Any:
        """Handle resource request for this feature"""
        pass
