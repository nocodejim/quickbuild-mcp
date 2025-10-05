"""
Tests for data models
"""
import pytest
from datetime import datetime

from src.models import Configuration, Build, Agent, Change


class TestConfiguration:
    """Test Configuration model"""
    
    def test_configuration_creation(self):
        """Test creating a configuration"""
        config = Configuration(
            id="123",
            name="Test Config",
            description="Test description",
            parent_id="456",
            enabled=True
        )
        
        assert config.id == "123"
        assert config.name == "Test Config"
        assert config.description == "Test description"
        assert config.parent_id == "456"
        assert config.enabled is True
    
    def test_configuration_without_parent(self):
        """Test configuration without parent"""
        config = Configuration(
            id="123",
            name="Root Config",
            description="Root configuration",
            parent_id=None,
            enabled=False
        )
        
        assert config.parent_id is None
        assert config.enabled is False


class TestBuild:
    """Test Build model"""
    
    def test_build_creation(self):
        """Test creating a build"""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        end_time = datetime(2024, 1, 1, 12, 30, 0)
        
        build = Build(
            id="456",
            configuration_id="123",
            version="1.0.0",
            status="SUCCESSFUL",
            start_time=start_time,
            end_time=end_time,
            success=True
        )
        
        assert build.id == "456"
        assert build.configuration_id == "123"
        assert build.version == "1.0.0"
        assert build.status == "SUCCESSFUL"
        assert build.start_time == start_time
        assert build.end_time == end_time
        assert build.success is True
    
    def test_build_without_end_time(self):
        """Test build without end time (running build)"""
        build = Build(
            id="789",
            configuration_id="123",
            version="1.1.0",
            status="RUNNING",
            start_time=datetime.now(),
            end_time=None,
            success=False
        )
        
        assert build.end_time is None
        assert build.success is False


class TestAgent:
    """Test Agent model"""
    
    def test_agent_creation(self):
        """Test creating an agent"""
        last_contact = datetime(2024, 1, 1, 12, 0, 0)
        
        agent = Agent(
            name="agent-1",
            status="online",
            last_contact=last_contact,
            ip_address="192.168.1.100",
            port=8810
        )
        
        assert agent.name == "agent-1"
        assert agent.status == "online"
        assert agent.last_contact == last_contact
        assert agent.ip_address == "192.168.1.100"
        assert agent.port == 8810


class TestChange:
    """Test Change model"""
    
    def test_change_creation(self):
        """Test creating a change"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        files = ["src/test.py", "README.md"]
        
        change = Change(
            revision="abc123",
            author="developer@example.com",
            message="Test commit",
            timestamp=timestamp,
            files=files
        )
        
        assert change.revision == "abc123"
        assert change.author == "developer@example.com"
        assert change.message == "Test commit"
        assert change.timestamp == timestamp
        assert change.files == files
    
    def test_change_with_empty_files(self):
        """Test change with no files"""
        change = Change(
            revision="def456",
            author="another@example.com",
            message="Empty commit",
            timestamp=datetime.now(),
            files=[]
        )
        
        assert change.files == []