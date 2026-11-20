from abc import ABC, abstractmethod
from typing import Any, List

from mcp.types import Resource, ResourceTemplate, Tool


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
