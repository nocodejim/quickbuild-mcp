"""
Tests for changes feature
"""
import pytest
import json
from unittest.mock import AsyncMock

from mcp.types import Resource

from src.features.changes.feature import ChangesFeature
from src.models import Change


class TestChangesFeature:
    """Test ChangesFeature"""
    
    @pytest.fixture
    def feature(self, mock_qb_client):
        """Create changes feature for testing"""
        return ChangesFeature(mock_qb_client)
    
    def test_get_tools(self, feature):
        """Test getting tools from changes feature"""
        tools = feature.get_tools()
        
        assert tools == []  # No tools in MVP
    
    def test_get_resources(self, feature):
        """Test getting resources from changes feature"""
        resources = feature.get_resources()
        
        assert len(resources) == 1
        assert isinstance(resources[0], Resource)
        # URI gets URL encoded, so check the decoded version
        assert "changes://build/" in str(resources[0].uri)
        assert "build_id" in str(resources[0].uri)
        assert resources[0].name == "Build Changes"
        assert resources[0].mimeType == "application/json"
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_not_implemented(self, feature):
        """Test that tool calls are not implemented"""
        with pytest.raises(NotImplementedError):
            await feature.handle_tool_call("test_tool", {})
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_build_changes(self, feature, sample_change):
        """Test handling build changes resource request"""
        feature.qb_client.get_build_changes.return_value = [sample_change]
        
        result = await feature.handle_resource_request("changes://build/456")
        data = json.loads(result)
        
        assert data["build_id"] == "456"
        assert data["count"] == 1
        assert len(data["changes"]) == 1
        
        change_data = data["changes"][0]
        assert change_data["revision"] == "abc123"
        assert change_data["author"] == "developer@example.com"
        assert change_data["message"] == "Test commit"
        assert change_data["files"] == ["src/test.py", "README.md"]
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_unknown_uri(self, feature):
        """Test handling unknown resource URI"""
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await feature.handle_resource_request("unknown://uri")
    
    @pytest.mark.asyncio
    async def test_get_build_changes_success(self, feature, sample_change):
        """Test successful build changes retrieval"""
        feature.qb_client.get_build_changes.return_value = [sample_change]
        
        result = await feature._get_build_changes("456")
        data = json.loads(result)
        
        assert data["build_id"] == "456"
        assert data["count"] == 1
        assert data["changes"][0]["revision"] == "abc123"
        assert data["changes"][0]["author"] == "developer@example.com"
        assert data["changes"][0]["message"] == "Test commit"
        assert data["changes"][0]["files"] == ["src/test.py", "README.md"]
    
    @pytest.mark.asyncio
    async def test_get_build_changes_multiple(self, feature, sample_change):
        """Test getting multiple build changes"""
        changes = [
            Change("abc123", "dev1@example.com", "First commit", sample_change.timestamp, ["file1.py"]),
            Change("def456", "dev2@example.com", "Second commit", sample_change.timestamp, ["file2.py", "file3.py"])
        ]
        feature.qb_client.get_build_changes.return_value = changes
        
        result = await feature._get_build_changes("456")
        data = json.loads(result)
        
        assert data["count"] == 2
        assert len(data["changes"]) == 2
        assert data["changes"][0]["revision"] == "abc123"
        assert data["changes"][1]["revision"] == "def456"
        assert len(data["changes"][1]["files"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_build_changes_empty(self, feature):
        """Test getting changes when none exist"""
        feature.qb_client.get_build_changes.return_value = []
        
        result = await feature._get_build_changes("456")
        data = json.loads(result)
        
        assert data["build_id"] == "456"
        assert data["count"] == 0
        assert data["changes"] == []
    
    @pytest.mark.asyncio
    async def test_get_build_changes_with_error(self, feature):
        """Test getting build changes with API error"""
        feature.qb_client.get_build_changes.side_effect = Exception("Changes API Error")
        
        result = await feature._get_build_changes("456")
        data = json.loads(result)
        
        assert "error" in data
        assert data["error"] == "Changes API Error"
    
    @pytest.mark.asyncio
    async def test_handle_resource_request_extracts_build_id(self, feature, sample_change):
        """Test that build ID is correctly extracted from URI"""
        feature.qb_client.get_build_changes.return_value = [sample_change]
        
        # Test with different build IDs
        await feature.handle_resource_request("changes://build/123")
        feature.qb_client.get_build_changes.assert_called_with("123")
        
        await feature.handle_resource_request("changes://build/abc-def-456")
        feature.qb_client.get_build_changes.assert_called_with("abc-def-456")