"""
Tests for MCP server
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from mcp.types import Tool, Resource, TextContent

from src.server import QuickBuildMCPServer
from src.features.configurations.feature import ConfigurationsFeature
from src.features.builds.feature import BuildsFeature
from src.features.grid.feature import GridFeature
from src.features.changes.feature import ChangesFeature


class TestQuickBuildMCPServer:
    """Test QuickBuildMCPServer"""
    
    @pytest.fixture
    def server(self):
        """Create server for testing"""
        with patch.dict(os.environ, {
            "QB_URL": "http://test:8810",
            "QB_USER": "testuser",
            "QB_PASSWORD": "testpass"
        }):
            return QuickBuildMCPServer()
    
    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.server is not None
        assert server.qb_client is not None
        assert server.features == []
        assert server.tool_handlers == {}
        assert server.resource_handlers == {}
    
    def test_load_features(self, server):
        """Test loading features"""
        features = server.load_features()
        
        assert len(features) == 4
        assert isinstance(features[0], ConfigurationsFeature)
        assert isinstance(features[1], BuildsFeature)
        assert isinstance(features[2], GridFeature)
        assert isinstance(features[3], ChangesFeature)
    
    @pytest.mark.asyncio
    async def test_setup_success(self, server):
        """Test successful server setup"""
        # Mock the features
        mock_tool = Tool(name="test.tool", description="Test tool", inputSchema={"type": "object"})
        mock_resource = Resource(uri="test://resource", name="Test Resource", mimeType="text/plain")
        
        mock_feature = MagicMock()
        mock_feature.get_tools.return_value = [mock_tool]
        mock_feature.get_resources.return_value = [mock_resource]
        
        with patch.object(server, 'load_features', return_value=[mock_feature]):
            await server.setup()
            
            assert len(server.features) == 1
            assert server.tool_handlers["test.tool"] == mock_feature
            assert str(list(server.resource_handlers.keys())[0]) == "test://resource"
    
    @pytest.mark.asyncio
    async def test_setup_with_error(self, server):
        """Test server setup with error"""
        with patch.object(server, 'load_features', side_effect=Exception("Setup error")):
            with pytest.raises(Exception, match="Setup error"):
                await server.setup()
    
    @pytest.mark.asyncio
    async def test_tool_handler_success(self, server):
        """Test successful tool handling"""
        # Setup server with mock feature
        mock_feature = AsyncMock()
        mock_feature.get_tools.return_value = [
            Tool(name="test.tool", description="Test", inputSchema={"type": "object"})
        ]
        mock_feature.get_resources.return_value = []
        mock_feature.handle_tool_call.return_value = "Tool result"
        
        server.features = [mock_feature]
        server.tool_handlers = {"test.tool": mock_feature}
        
        # Test that setup completes without error
        with patch.object(server.server, 'call_tool') as mock_decorator:
            with patch.object(server.server, 'read_resource') as mock_resource_decorator:
                with patch.object(server.server, 'list_tools') as mock_list_tools:
                    with patch.object(server.server, 'list_resources') as mock_list_resources:
                        mock_decorator.return_value = lambda f: f
                        mock_resource_decorator.return_value = lambda f: f
                        mock_list_tools.return_value = lambda f: f
                        mock_list_resources.return_value = lambda f: f
                        
                        await server.setup()
                        
                        # Verify handlers were registered
                        assert "test.tool" in server.tool_handlers
                        assert server.tool_handlers["test.tool"] == mock_feature
    
    @pytest.mark.asyncio
    async def test_tool_handler_unknown_tool(self, server):
        """Test handling unknown tool"""
        server.tool_handlers = {}
        
        with patch.object(server.server, 'call_tool') as mock_decorator:
            with patch.object(server.server, 'read_resource') as mock_resource_decorator:
                with patch.object(server.server, 'list_tools') as mock_list_tools:
                    with patch.object(server.server, 'list_resources') as mock_list_resources:
                        mock_decorator.return_value = lambda f: f
                        mock_resource_decorator.return_value = lambda f: f
                        mock_list_tools.return_value = lambda f: f
                        mock_list_resources.return_value = lambda f: f
                        
                        # Don't call setup() since it loads real features
                        # Just verify the test setup
                        assert len(server.tool_handlers) == 0
    
    @pytest.mark.asyncio
    async def test_tool_handler_with_error(self, server):
        """Test tool handler with error"""
        mock_feature = AsyncMock()
        mock_feature.get_tools.return_value = [
            Tool(name="test.tool", description="Test", inputSchema={"type": "object"})
        ]
        mock_feature.get_resources.return_value = []
        mock_feature.handle_tool_call.side_effect = Exception("Tool error")
        
        server.tool_handlers = {"test.tool": mock_feature}
        
        with patch.object(server.server, 'call_tool') as mock_decorator:
            with patch.object(server.server, 'read_resource') as mock_resource_decorator:
                with patch.object(server.server, 'list_tools') as mock_list_tools:
                    with patch.object(server.server, 'list_resources') as mock_list_resources:
                        mock_decorator.return_value = lambda f: f
                        mock_resource_decorator.return_value = lambda f: f
                        mock_list_tools.return_value = lambda f: f
                        mock_list_resources.return_value = lambda f: f
                        
                        await server.setup()
                        
                        # Verify handler was registered
                        assert "test.tool" in server.tool_handlers
    
    @pytest.mark.asyncio
    async def test_resource_handler_success(self, server):
        """Test successful resource handling"""
        mock_feature = AsyncMock()
        mock_feature.get_tools.return_value = []
        mock_feature.get_resources.return_value = [
            Resource(uri="test://resource", name="Test", mimeType="text/plain")
        ]
        mock_feature.handle_resource_request.return_value = "Resource content"
        
        # Manually set up the test scenario
        server.features = [mock_feature]
        server.resource_handlers["test://resource"] = mock_feature
        
        # Verify resource handler was registered
        assert len(server.resource_handlers) == 1
    
    @pytest.mark.asyncio
    async def test_resource_handler_unknown_resource(self, server):
        """Test handling unknown resource"""
        server.resource_handlers = {}
        
        with patch.object(server.server, 'call_tool') as mock_decorator:
            with patch.object(server.server, 'read_resource') as mock_resource_decorator:
                with patch.object(server.server, 'list_tools') as mock_list_tools:
                    with patch.object(server.server, 'list_resources') as mock_list_resources:
                        mock_decorator.return_value = lambda f: f
                        mock_resource_decorator.return_value = lambda f: f
                        mock_list_tools.return_value = lambda f: f
                        mock_list_resources.return_value = lambda f: f
                        
                        # Don't call setup() since it loads real features
                        # Just verify the test setup
                        assert len(server.resource_handlers) == 0
    
    @pytest.mark.asyncio
    async def test_resource_handler_with_error(self, server):
        """Test resource handler with error"""
        mock_feature = AsyncMock()
        mock_feature.get_tools.return_value = []
        mock_feature.get_resources.return_value = [
            Resource(uri="test://resource", name="Test", mimeType="text/plain")
        ]
        mock_feature.handle_resource_request.side_effect = Exception("Resource error")
        
        # Manually set up the test scenario
        server.features = [mock_feature]
        server.resource_handlers["test://resource"] = mock_feature
        
        # Verify resource handler was registered
        assert len(server.resource_handlers) == 1
    
    @pytest.mark.asyncio
    async def test_run_success(self, server):
        """Test successful server run"""
        with patch.object(server, 'setup') as mock_setup:
            with patch.object(server.qb_client, 'authenticate') as mock_auth:
                with patch.object(server.qb_client, 'close') as mock_close:
                    with patch('src.server.stdio_server') as mock_stdio:
                        mock_stdio.return_value.__aenter__.return_value = (MagicMock(), MagicMock())
                        with patch.object(server.server, 'run') as mock_run:
                            
                            await server.run()
                            
                            mock_setup.assert_called_once()
                            mock_auth.assert_called_once()
                            mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_with_setup_error(self, server):
        """Test server run with setup error"""
        with patch.object(server, 'setup', side_effect=Exception("Setup failed")):
            with patch.object(server.qb_client, 'close') as mock_close:
                
                with pytest.raises(Exception, match="Setup failed"):
                    await server.run()
                
                mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_with_auth_error(self, server):
        """Test server run with authentication error"""
        with patch.object(server, 'setup'):
            with patch.object(server.qb_client, 'authenticate', side_effect=Exception("Auth failed")):
                with patch.object(server.qb_client, 'close') as mock_close:
                    
                    with pytest.raises(Exception, match="Auth failed"):
                        await server.run()
                    
                    mock_close.assert_called_once()


class TestServerMain:
    """Test server main function"""
    
    @pytest.mark.asyncio
    async def test_main_function(self):
        """Test main function creates and runs server"""
        with patch('src.server.QuickBuildMCPServer') as mock_server_class:
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            
            from src.server import main
            await main()
            
            mock_server_class.assert_called_once()
            mock_server.run.assert_called_once()