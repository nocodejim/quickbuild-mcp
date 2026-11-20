"""
Tests for system feature
"""
import json
import pytest

from mcp.types import Tool

from src.features.system.feature import SystemFeature


class TestSystemFeature:
    """Test SystemFeature"""

    @pytest.fixture
    def feature(self, mock_qb_client):
        """Create system feature for testing"""
        return SystemFeature(mock_qb_client)

    def test_get_tools(self, feature):
        """Test getting tools from system feature"""
        tools = feature.get_tools()

        assert len(tools) == 2

        backup_tool = next(t for t in tools if t.name == "system.backup_database")
        assert isinstance(backup_tool, Tool)
        assert "backup_path" in backup_tool.input_schema["properties"]

        version_tool = next(t for t in tools if t.name == "system.get_version")
        assert isinstance(version_tool, Tool)
        assert version_tool.input_schema["properties"] == {}

    def test_get_resources(self, feature):
        """Test getting resources from system feature"""
        assert feature.get_resources() == []

    @pytest.mark.asyncio
    async def test_handle_tool_call_backup_database(self, feature):
        """Test initiating a database backup without explicit path"""
        feature.qb_client.backup_database.return_value = {
            "status": "initiated",
            "message": "Database backup initiated successfully",
        }

        result = await feature.handle_tool_call("system.backup_database", {})
        data = json.loads(result)

        assert data["status"] == "initiated"
        feature.qb_client.backup_database.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_handle_tool_call_backup_database_with_path(self, feature):
        """Test initiating a database backup with explicit backup_path"""
        feature.qb_client.backup_database.return_value = {
            "status": "initiated",
            "backup_path": "/backups/qb.zip",
            "message": "Database backup initiated successfully",
        }

        result = await feature.handle_tool_call(
            "system.backup_database", {"backup_path": "/backups/qb.zip"}
        )
        data = json.loads(result)

        assert data["backup_path"] == "/backups/qb.zip"
        feature.qb_client.backup_database.assert_called_once_with("/backups/qb.zip")

    @pytest.mark.asyncio
    async def test_handle_tool_call_backup_database_error(self, feature):
        """Test database backup error handling"""
        feature.qb_client.backup_database.side_effect = Exception("Permission denied")

        result = await feature.handle_tool_call("system.backup_database", {})
        data = json.loads(result)

        assert data["error"] == "Permission denied"

    @pytest.mark.asyncio
    async def test_handle_tool_call_get_version(self, feature):
        """Test getting QuickBuild server version"""
        feature.qb_client.get_version.return_value = {"version": "14.0.32"}

        result = await feature.handle_tool_call("system.get_version", {})
        data = json.loads(result)

        assert data["version"] == "14.0.32"
        feature.qb_client.get_version.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_tool_call_get_version_error(self, feature):
        """Test get_version error handling"""
        feature.qb_client.get_version.side_effect = Exception("Server unreachable")

        result = await feature.handle_tool_call("system.get_version", {})
        data = json.loads(result)

        assert data["error"] == "Server unreachable"

    @pytest.mark.asyncio
    async def test_handle_tool_call_unknown_tool(self, feature):
        """Test unknown tool raises ValueError"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await feature.handle_tool_call("system.unknown", {})

    @pytest.mark.asyncio
    async def test_handle_resource_request_not_implemented(self, feature):
        """Test resource requests raise ValueError"""
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await feature.handle_resource_request("system://status")
