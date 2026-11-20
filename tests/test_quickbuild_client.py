"""
Tests for QuickBuild API client
"""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import httpx

from src.quickbuild_client import QuickBuildClient
from src.exceptions import (
    AuthenticationError, ResourceNotFoundError, QuickBuildServerError,
    QuickBuildUnavailableError
)
from src.models import Configuration, Build, Agent, Change


class TestQuickBuildClientInit:
    """Test QuickBuild client initialization"""
    
    @patch.dict(os.environ, {
        "QB_URL": "http://test:8810",
        "QB_USER": "testuser",
        "QB_PASSWORD": "testpass"
    })
    def test_client_initialization(self):
        """Test client initialization with environment variables"""
        client = QuickBuildClient()
        
        assert client.base_url == "http://test:8810"
        assert client.username == "testuser"
        assert client.password == "testpass"
        assert client.authenticated is False
    
    @patch.dict(os.environ, {
        "QB_URL": "http://test:8810",
        "QB_USER": "testuser"
    }, clear=True)
    def test_client_initialization_missing_password(self):
        """Test client initialization without password"""
        with pytest.raises(ValueError, match="QB_PASSWORD environment variable is required"):
            QuickBuildClient()
    
    def test_client_initialization_defaults(self):
        """Test client initialization with defaults"""
        with patch.dict(os.environ, {"QB_PASSWORD": "testpass"}, clear=True):
            client = QuickBuildClient()
            
            assert client.base_url == "http://localhost:8810"
            assert client.username == "admin"


class TestQuickBuildClientAuthentication:
    """Test authentication methods"""
    
    @pytest.fixture
    def client(self):
        """Create client for testing"""
        with patch.dict(os.environ, {
            "QB_URL": "http://test:8810",
            "QB_USER": "testuser",
            "QB_PASSWORD": "testpass"
        }):
            return QuickBuildClient()
    
    @pytest.mark.asyncio
    async def test_successful_authentication(self, client, mock_httpx_response):
        """Test successful authentication"""
        mock_httpx_response.status_code = 200
        
        with patch.object(client.client, 'post', return_value=mock_httpx_response):
            result = await client.authenticate()
            
            assert result is True
            assert client.authenticated is True
    
    @pytest.mark.asyncio
    async def test_failed_authentication(self, client):
        """Test failed authentication"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch.object(client.client, 'post', return_value=mock_response):
            with pytest.raises(AuthenticationError):
                await client.authenticate()
    
    @pytest.mark.asyncio
    async def test_authentication_connection_error(self, client):
        """Test authentication with connection error"""
        with patch.object(client.client, 'post', side_effect=httpx.ConnectError("Connection failed")):
            with pytest.raises(QuickBuildUnavailableError):
                await client.authenticate()

    @pytest.mark.asyncio
    async def test_authentication_timeout_error(self, client):
        """Test authentication with timeout error"""
        with patch.object(client.client, 'post', side_effect=httpx.TimeoutException("Request timed out")):
            with pytest.raises(QuickBuildUnavailableError):
                await client.authenticate()
    
    @pytest.mark.asyncio
    async def test_authentication_unexpected_error(self, client):
        """Test authentication with unexpected error"""
        with patch.object(client.client, 'post', side_effect=Exception("Unexpected error")):
            with pytest.raises(Exception):
                await client.authenticate()


class TestQuickBuildClientRequests:
    """Test request methods"""
    
    @pytest.fixture
    def authenticated_client(self):
        """Create authenticated client for testing"""
        with patch.dict(os.environ, {
            "QB_URL": "http://test:8810",
            "QB_USER": "testuser",
            "QB_PASSWORD": "testpass"
        }):
            client = QuickBuildClient()
            client.authenticated = True
            return client
    
    @pytest.mark.asyncio
    async def test_make_request_success(self, authenticated_client, mock_httpx_response):
        """Test successful request"""
        mock_httpx_response.json.return_value = {"result": "success"}
        
        with patch.object(authenticated_client.client, 'request', return_value=mock_httpx_response):
            result = await authenticated_client._make_request("GET", "test")
            
            assert result == {"result": "success"}
    
    @pytest.mark.asyncio
    async def test_make_request_401_retry(self, authenticated_client):
        """Test request with 401 triggers re-authentication"""
        # First call returns 401, second call succeeds
        mock_401_response = MagicMock()
        mock_401_response.status_code = 401
        
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"result": "success"}
        mock_success_response.content = b'{"result": "success"}'
        
        with patch.object(authenticated_client.client, 'request', side_effect=[mock_401_response, mock_success_response]):
            with patch.object(authenticated_client, 'authenticate', return_value=True):
                result = await authenticated_client._make_request("GET", "test")
                
                assert result == {"result": "success"}
    
    @pytest.mark.asyncio
    async def test_make_request_401_exhausted(self, authenticated_client):
        """Test request with persistent 401 raises AuthenticationError after retries"""
        mock_401_response = MagicMock()
        mock_401_response.status_code = 401

        with patch.object(authenticated_client.client, 'request', return_value=mock_401_response):
            with patch.object(authenticated_client, 'authenticate', return_value=True):
                with pytest.raises(AuthenticationError):
                    await authenticated_client._make_request("GET", "test")

    @pytest.mark.asyncio
    async def test_make_request_404_error(self, authenticated_client):
        """Test request with 404 error"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch.object(authenticated_client.client, 'request', return_value=mock_response):
            with pytest.raises(ResourceNotFoundError):
                await authenticated_client._make_request("GET", "test")
    
    @pytest.mark.asyncio
    async def test_make_request_500_retry(self, authenticated_client):
        """Test request with 500 error and retry"""
        mock_500_response = MagicMock()
        mock_500_response.status_code = 500
        
        with patch.object(authenticated_client.client, 'request', return_value=mock_500_response):
            with pytest.raises(QuickBuildServerError):
                await authenticated_client._make_request("GET", "test")
    
    @pytest.mark.asyncio
    async def test_make_request_connection_error_retry(self, authenticated_client):
        """Test request with connection error and retry"""
        with patch.object(authenticated_client.client, 'request', side_effect=httpx.ConnectError("Connection failed")):
            with pytest.raises(QuickBuildUnavailableError):
                await authenticated_client._make_request("GET", "test")

    @pytest.mark.asyncio
    async def test_make_request_timeout_error_retry(self, authenticated_client):
        """Test request with timeout error and retry"""
        with patch.object(authenticated_client.client, 'request', side_effect=httpx.TimeoutException("Timed out")):
            with pytest.raises(QuickBuildUnavailableError):
                await authenticated_client._make_request("GET", "test")

    @pytest.mark.asyncio
    async def test_make_request_plain_text_response(self, authenticated_client):
        """Test request handles non-JSON plain text response gracefully"""
        mock_text_response = MagicMock()
        mock_text_response.status_code = 200
        mock_text_response.content = b"14.0.32"
        mock_text_response.text = "14.0.32"
        mock_text_response.json.side_effect = ValueError("Not JSON")

        with patch.object(authenticated_client.client, 'request', return_value=mock_text_response):
            result = await authenticated_client._make_request("GET", "version")
            assert result == {"raw": "14.0.32"}


class TestQuickBuildClientMethods:
    """Test specific API methods"""
    
    @pytest.fixture
    def authenticated_client(self):
        """Create authenticated client for testing"""
        with patch.dict(os.environ, {
            "QB_URL": "http://test:8810",
            "QB_USER": "testuser",
            "QB_PASSWORD": "testpass"
        }):
            client = QuickBuildClient()
            client.authenticated = True
            return client
    
    @pytest.mark.asyncio
    async def test_get_configurations(self, authenticated_client):
        """Test getting configurations"""
        mock_response = [
            {
                "id": "123",
                "name": "Test Config",
                "description": "Test description",
                "parentId": None,
                "enabled": True
            }
        ]
        
        with patch.object(authenticated_client, 'get', return_value=mock_response):
            configs = await authenticated_client.get_configurations()
            
            assert len(configs) == 1
            assert isinstance(configs[0], Configuration)
            assert configs[0].id == "123"
            assert configs[0].name == "Test Config"
    
    @pytest.mark.asyncio
    async def test_get_configurations_single_response(self, authenticated_client):
        """Test getting configurations with single response"""
        mock_response = {
            "id": "123",
            "name": "Test Config",
            "description": "Test description",
            "parentId": "456",
            "enabled": False
        }
        
        with patch.object(authenticated_client, 'get', return_value=mock_response):
            configs = await authenticated_client.get_configurations()
            
            assert len(configs) == 1
            assert configs[0].parent_id == "456"
            assert configs[0].enabled is False
    
    @pytest.mark.asyncio
    async def test_get_latest_build_status(self, authenticated_client):
        """Test getting latest build status"""
        mock_response = [{
            "id": "456",
            "version": "1.0.0",
            "status": "SUCCESSFUL",
            "startTime": "2024-01-01T12:00:00Z",
            "endTime": "2024-01-01T12:30:00Z"
        }]
        
        with patch.object(authenticated_client, 'get', return_value=mock_response):
            build = await authenticated_client.get_latest_build_status("123")
            
            assert isinstance(build, Build)
            assert build.id == "456"
            assert build.configuration_id == "123"
            assert build.success is True
    
    @pytest.mark.asyncio
    async def test_get_latest_build_status_no_builds(self, authenticated_client):
        """Test getting build status when no builds exist"""
        with patch.object(authenticated_client, 'get', return_value=[]):
            build = await authenticated_client.get_latest_build_status("123")
            
            assert build is None
    
    @pytest.mark.asyncio
    async def test_trigger_build(self, authenticated_client):
        """Test triggering a build"""
        mock_response = {
            "id": "789",
            "status": "QUEUED"
        }
        
        with patch.object(authenticated_client, 'post', return_value=mock_response):
            result = await authenticated_client.trigger_build("123", {"VAR1": "value1"})
            
            assert result["build_id"] == "789"
            assert result["configuration_id"] == "123"
            assert result["status"] == "QUEUED"
            assert result["variables"] == {"VAR1": "value1"}
    
    @pytest.mark.asyncio
    async def test_trigger_build_no_variables(self, authenticated_client):
        """Test triggering build without variables"""
        mock_response = {
            "id": "789",
            "status": "QUEUED"
        }
        
        with patch.object(authenticated_client, 'post', return_value=mock_response):
            result = await authenticated_client.trigger_build("123")
            
            assert "variables" not in result
    
    @pytest.mark.asyncio
    async def test_get_agents(self, authenticated_client):
        """Test getting agents"""
        mock_response = [{
            "name": "agent-1",
            "status": "online",
            "lastContact": "2024-01-01T12:00:00Z",
            "ipAddress": "192.168.1.100",
            "port": 8810
        }]
        
        with patch.object(authenticated_client, 'get', return_value=mock_response):
            agents = await authenticated_client.get_agents()
            
            assert len(agents) == 1
            assert isinstance(agents[0], Agent)
            assert agents[0].name == "agent-1"
            assert agents[0].status == "online"
    
    @pytest.mark.asyncio
    async def test_get_build_changes(self, authenticated_client):
        """Test getting build changes"""
        mock_response = [{
            "revision": "abc123",
            "author": "developer@example.com",
            "message": "Test commit",
            "timestamp": "2024-01-01T12:00:00Z",
            "files": ["src/test.py"]
        }]
        
        with patch.object(authenticated_client, 'get', return_value=mock_response):
            changes = await authenticated_client.get_build_changes("456")
            
            assert len(changes) == 1
            assert isinstance(changes[0], Change)
            assert changes[0].revision == "abc123"
            assert changes[0].author == "developer@example.com"
    
    @pytest.mark.asyncio
    async def test_close(self, authenticated_client):
        """Test closing the client"""
        with patch.object(authenticated_client.client, 'aclose') as mock_close:
            await authenticated_client.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_responses_return_empty_lists(self, authenticated_client):
        """Test empty dict or list responses return empty lists cleanly"""
        with patch.object(authenticated_client, 'get', return_value={}):
            assert await authenticated_client.get_configurations() == []
            assert await authenticated_client.get_agents() == []
            assert await authenticated_client.get_build_changes("123") == []

    @pytest.mark.asyncio
    async def test_ttl_caching_and_clear_cache(self, authenticated_client):
        """Test TTL caching for configurations and agents and manual cache clearing"""
        mock_configs = [{"id": "1", "name": "Build", "description": "", "parentId": None, "enabled": True}]
        with patch.object(authenticated_client, 'get', return_value=mock_configs) as mock_get:
            first = await authenticated_client.get_configurations()
            second = await authenticated_client.get_configurations()
            assert len(first) == 1
            assert first == second
            mock_get.assert_called_once()

            authenticated_client.clear_cache("configurations")
            await authenticated_client.get_configurations()
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_version(self, authenticated_client):
        """Test retrieving QuickBuild version"""
        with patch.object(authenticated_client, 'get', return_value={"raw": "14.0.32"}):
            version_info = await authenticated_client.get_version()
            assert version_info["version"] == "14.0.32"

    @pytest.mark.asyncio
    async def test_backup_database(self, authenticated_client):
        """Test initiating database backup"""
        with patch.object(authenticated_client, 'post', return_value={"raw": "/backups/qb.zip"}) as mock_post:
            result = await authenticated_client.backup_database("/backups/qb.zip")
            assert result["status"] == "initiated"
            assert result["backup_path"] == "/backups/qb.zip"
            assert result["details"] == "/backups/qb.zip"
            mock_post.assert_called_once_with("backup", {"backupPath": "/backups/qb.zip"})

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager closes client on exit"""
        with patch.dict(os.environ, {"QB_PASSWORD": "testpass"}):
            with patch.object(httpx.AsyncClient, 'aclose', new_callable=AsyncMock) as mock_close:
                async with QuickBuildClient():
                    pass
                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ttl_cache_expiration(self):
        """Test expired cache entry triggers fresh API fetch"""
        with patch.dict(os.environ, {"QB_PASSWORD": "testpass"}):
            client = QuickBuildClient(cache_ttl_configs=1, cache_ttl_agents=1)
            client.authenticated = True
            mock_configs = [{"id": "1", "name": "Build", "description": "", "parentId": None, "enabled": True}]
            with patch.object(client, 'get', return_value=mock_configs) as mock_get:
                with patch('src.quickbuild_client.time.monotonic', side_effect=[100.0, 102.0, 102.0]):
                    await client.get_configurations()
                    await client.get_configurations()
                    assert mock_get.call_count == 2
            await client.close()