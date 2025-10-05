"""
Tests for configurations feature
"""
import pytest
import json
from unittest.mock import AsyncMock

from mcp.types import Resource

from src.features.configurations.feature import ConfigurationsFeature
from src.models import Configuration


class TestConfigurationsFeature:
    """Test ConfigurationsFeature"""
    
    @pytest.fixture
    def feature(self, mock_qb_client):
        """Create configurations feature for testing"""
        return ConfigurationsFeature(mock_qb_client)
    
    def test_get_tools(self, feature):
        """Test getting tools from configurations feature"""
        tools = feature.get_tools()
        
        assert tools == []  # No tools in MVP
    
    def test_get_resources(self, feature):
        """Test getting resources from configurations feature"""
        resources = feature.get_resources()
        
        assert len(resources) == 1
        assert isinstance(resources[0], Resource)
        assert str(resources[0].uri) == "configurations://list"
        assert resources[0].name == "Build Configurations"
        assert resources[0].mimeType == "application/json"
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_not_implemented(self, feature):
        """Test that tool calls are not implemented"""
        with pytest.raises(NotImplementedError):
            await feature.handle_tool_call("test_tool", {})
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_list(self, feature, sample_configuration):
        """Test handling configurations list resource request"""
        feature.qb_client.get_configurations.return_value = [sample_configuration]
        
        result = await feature.handle_resource_request("configurations://list")
        
        # Parse JSON result
        data = json.loads(result)
        
        assert data["count"] == 1
        assert len(data["configurations"]) == 1
        assert data["configurations"][0]["id"] == "123"
        assert data["configurations"][0]["name"] == "Test Config"
        assert data["configurations"][0]["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_unknown_uri(self, feature):
        """Test handling unknown resource URI"""
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await feature.handle_resource_request("unknown://uri")
    
    @pytest.mark.asyncio
    async def test_list_configurations_success(self, feature, sample_configuration):
        """Test successful configuration listing"""
        feature.qb_client.get_configurations.return_value = [sample_configuration]
        
        result = await feature._list_configurations()
        data = json.loads(result)
        
        assert data["count"] == 1
        assert data["configurations"][0]["id"] == "123"
        assert data["configurations"][0]["name"] == "Test Config"
        assert data["configurations"][0]["description"] == "Test configuration"
        assert data["configurations"][0]["parent_id"] is None
        assert data["configurations"][0]["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_list_configurations_multiple(self, feature):
        """Test listing multiple configurations"""
        configs = [
            Configuration("1", "Config 1", "First config", None, True),
            Configuration("2", "Config 2", "Second config", "1", False)
        ]
        feature.qb_client.get_configurations.return_value = configs
        
        result = await feature._list_configurations()
        data = json.loads(result)
        
        assert data["count"] == 2
        assert len(data["configurations"]) == 2
        assert data["configurations"][1]["parent_id"] == "1"
        assert data["configurations"][1]["enabled"] is False
    
    @pytest.mark.asyncio
    async def test_list_configurations_empty(self, feature):
        """Test listing when no configurations exist"""
        feature.qb_client.get_configurations.return_value = []
        
        result = await feature._list_configurations()
        data = json.loads(result)
        
        assert data["count"] == 0
        assert data["configurations"] == []
    
    @pytest.mark.asyncio
    async def test_list_configurations_error(self, feature):
        """Test configuration listing with error"""
        feature.qb_client.get_configurations.side_effect = Exception("API Error")
        
        result = await feature._list_configurations()
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "API Error"