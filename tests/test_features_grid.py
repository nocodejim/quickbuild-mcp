"""
Tests for grid feature
"""
import pytest
import json
from unittest.mock import AsyncMock

from mcp.types import Tool

from src.features.grid.feature import GridFeature
from src.models import Agent


class TestGridFeature:
    """Test GridFeature"""
    
    @pytest.fixture
    def feature(self, mock_qb_client):
        """Create grid feature for testing"""
        return GridFeature(mock_qb_client)
    
    def test_get_tools(self, feature):
        """Test getting tools from grid feature"""
        tools = feature.get_tools()
        
        assert len(tools) == 1
        
        # Check grid.list_agents tool
        list_tool = tools[0]
        assert isinstance(list_tool, Tool)
        assert list_tool.name == "grid.list_agents"
        assert list_tool.inputSchema["properties"] == {}
        assert list_tool.inputSchema["additionalProperties"] is False
    
    def test_get_resources(self, feature):
        """Test getting resources from grid feature"""
        resources = feature.get_resources()
        
        assert resources == []  # No resources in MVP
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_list_agents(self, feature, sample_agent):
        """Test handling list_agents tool call"""
        feature.qb_client.get_agents.return_value = [sample_agent]
        
        result = await feature.handle_tool_call("grid.list_agents", {})
        data = json.loads(result)
        
        assert data["count"] == 1
        assert data["online_count"] == 1
        assert data["offline_count"] == 0
        assert len(data["agents"]) == 1
        
        agent_data = data["agents"][0]
        assert agent_data["name"] == "agent-1"
        assert agent_data["status"] == "online"
        assert agent_data["ip_address"] == "192.168.1.100"
        assert agent_data["port"] == 8810
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_list_agents_multiple(self, feature, sample_agent):
        """Test listing multiple agents with different statuses"""
        agents = [
            Agent("agent-1", "online", sample_agent.last_contact, "192.168.1.100", 8810),
            Agent("agent-2", "offline", sample_agent.last_contact, "192.168.1.101", 8810),
            Agent("agent-3", "online", sample_agent.last_contact, "192.168.1.102", 8810)
        ]
        feature.qb_client.get_agents.return_value = agents
        
        result = await feature.handle_tool_call("grid.list_agents", {})
        data = json.loads(result)
        
        assert data["count"] == 3
        assert data["online_count"] == 2
        assert data["offline_count"] == 1
        assert len(data["agents"]) == 3
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_list_agents_empty(self, feature):
        """Test listing when no agents exist"""
        feature.qb_client.get_agents.return_value = []
        
        result = await feature.handle_tool_call("grid.list_agents", {})
        data = json.loads(result)
        
        assert data["count"] == 0
        assert data["online_count"] == 0
        assert data["offline_count"] == 0
        assert data["agents"] == []
    
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
    async def test_list_agents_with_error(self, feature):
        """Test list_agents with API error"""
        feature.qb_client.get_agents.side_effect = Exception("Grid API Error")
        
        result = await feature._list_agents()
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "Grid API Error"
    
    @pytest.mark.asyncio
    async def test_list_agents_case_insensitive_status(self, feature, sample_agent):
        """Test agent status counting is case insensitive"""
        agents = [
            Agent("agent-1", "ONLINE", sample_agent.last_contact, "192.168.1.100", 8810),
            Agent("agent-2", "offline", sample_agent.last_contact, "192.168.1.101", 8810),
            Agent("agent-3", "Online", sample_agent.last_contact, "192.168.1.102", 8810)
        ]
        feature.qb_client.get_agents.return_value = agents
        
        result = await feature._list_agents()
        data = json.loads(result)
        
        assert data["online_count"] == 2
        assert data["offline_count"] == 1