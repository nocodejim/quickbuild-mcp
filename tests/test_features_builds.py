"""
Tests for builds feature
"""
import pytest
import json
from unittest.mock import AsyncMock
from datetime import datetime

from mcp.types import Tool

from src.features.builds.feature import BuildsFeature
from src.models import Build


class TestBuildsFeature:
    """Test BuildsFeature"""
    
    @pytest.fixture
    def feature(self, mock_qb_client):
        """Create builds feature for testing"""
        return BuildsFeature(mock_qb_client)
    
    def test_get_tools(self, feature):
        """Test getting tools from builds feature"""
        tools = feature.get_tools()
        
        assert len(tools) == 2
        
        # Check builds.get_latest_status tool
        status_tool = next(t for t in tools if t.name == "builds.get_latest_status")
        assert isinstance(status_tool, Tool)
        assert "configuration_id" in status_tool.inputSchema["properties"]
        assert status_tool.inputSchema["required"] == ["configuration_id"]
        
        # Check builds.trigger tool
        trigger_tool = next(t for t in tools if t.name == "builds.trigger")
        assert isinstance(trigger_tool, Tool)
        assert "configuration_id" in trigger_tool.inputSchema["properties"]
        assert "variables" in trigger_tool.inputSchema["properties"]
        assert trigger_tool.inputSchema["required"] == ["configuration_id"]
    
    def test_get_resources(self, feature):
        """Test getting resources from builds feature"""
        resources = feature.get_resources()
        
        assert resources == []  # No resources in MVP
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_get_latest_status(self, feature, sample_build):
        """Test handling get_latest_status tool call"""
        feature.qb_client.get_latest_build_status.return_value = sample_build
        
        result = await feature.handle_tool_call("builds.get_latest_status", {"configuration_id": "123"})
        data = json.loads(result)
        
        assert data["configuration_id"] == "123"
        assert data["build_id"] == "456"
        assert data["version"] == "1.0.0"
        assert data["status"] == "SUCCESSFUL"
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_get_latest_status_no_builds(self, feature):
        """Test get_latest_status when no builds exist"""
        feature.qb_client.get_latest_build_status.return_value = None
        
        result = await feature.handle_tool_call("builds.get_latest_status", {"configuration_id": "123"})
        data = json.loads(result)
        
        assert data["configuration_id"] == "123"
        assert data["message"] == "No builds found for this configuration"
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_trigger_build(self, feature):
        """Test handling trigger build tool call"""
        mock_result = {
            "build_id": "789",
            "configuration_id": "123",
            "status": "QUEUED",
            "message": "Build triggered successfully for configuration 123",
            "variables": {"VAR1": "value1"}
        }
        feature.qb_client.trigger_build.return_value = mock_result
        
        result = await feature.handle_tool_call("builds.trigger", {
            "configuration_id": "123",
            "variables": {"VAR1": "value1"}
        })
        data = json.loads(result)
        
        assert data["build_id"] == "789"
        assert data["configuration_id"] == "123"
        assert data["status"] == "QUEUED"
        assert data["variables"]["VAR1"] == "value1"
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_trigger_build_no_variables(self, feature):
        """Test triggering build without variables"""
        mock_result = {
            "build_id": "789",
            "configuration_id": "123",
            "status": "QUEUED",
            "message": "Build triggered successfully for configuration 123"
        }
        feature.qb_client.trigger_build.return_value = mock_result
        
        result = await feature.handle_tool_call("builds.trigger", {"configuration_id": "123"})
        data = json.loads(result)
        
        assert data["build_id"] == "789"
        assert "variables" not in data
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_unknown_tool(self, feature):
        """Test handling unknown tool call"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await feature.handle_tool_call("unknown.tool", {})
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_not_implemented(self, feature):
        """Test that resource requests are not implemented"""
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await feature.handle_resource_request("test://uri")
    
    @pytest.mark.asyncio
    async def test_get_latest_status_missing_config_id(self, feature):
        """Test get_latest_status without configuration_id"""
        result = await feature._get_latest_status({})
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "configuration_id is required"
    
    @pytest.mark.asyncio
    async def test_get_latest_status_with_error(self, feature):
        """Test get_latest_status with API error"""
        feature.qb_client.get_latest_build_status.side_effect = Exception("API Error")
        
        result = await feature._get_latest_status({"configuration_id": "123"})
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "API Error"
    
    @pytest.mark.asyncio
    async def test_trigger_build_missing_config_id(self, feature):
        """Test trigger_build without configuration_id"""
        result = await feature._trigger_build({})
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "configuration_id is required"
    
    @pytest.mark.asyncio
    async def test_trigger_build_with_error(self, feature):
        """Test trigger_build with API error"""
        feature.qb_client.trigger_build.side_effect = Exception("Trigger failed")
        
        result = await feature._trigger_build({"configuration_id": "123"})
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "Trigger failed"