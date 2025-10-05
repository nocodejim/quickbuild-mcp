"""
Pytest configuration and fixtures
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.quickbuild_client import QuickBuildClient
from src.models import Configuration, Build, Agent, Change

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def mock_qb_client():
    """Mock QuickBuild client for testing"""
    client = AsyncMock(spec=QuickBuildClient)
    client.authenticated = True
    return client


@pytest.fixture
def sample_configuration():
    """Sample configuration for testing"""
    return Configuration(
        id="123",
        name="Test Config",
        description="Test configuration",
        parent_id=None,
        enabled=True
    )


@pytest.fixture
def sample_build():
    """Sample build for testing"""
    return Build(
        id="456",
        configuration_id="123",
        version="1.0.0",
        status="SUCCESSFUL",
        start_time=datetime(2024, 1, 1, 12, 0, 0),
        end_time=datetime(2024, 1, 1, 12, 30, 0),
        success=True
    )


@pytest.fixture
def sample_agent():
    """Sample agent for testing"""
    return Agent(
        name="agent-1",
        status="online",
        last_contact=datetime(2024, 1, 1, 12, 0, 0),
        ip_address="192.168.1.100",
        port=8810
    )


@pytest.fixture
def sample_change():
    """Sample change for testing"""
    return Change(
        revision="abc123",
        author="developer@example.com",
        message="Test commit",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        files=["src/test.py", "README.md"]
    )


@pytest.fixture
def mock_httpx_response():
    """Mock httpx response"""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": "success"}
    response.content = b'{"status": "success"}'
    response.text = '{"status": "success"}'
    return response