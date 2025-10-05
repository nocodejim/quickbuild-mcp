"""
Tests for base feature class
"""
import pytest
from abc import ABC

from src.features.base import Feature


class TestFeatureBase:
    """Test Feature base class"""
    
    def test_feature_is_abstract(self):
        """Test that Feature is an abstract base class"""
        assert issubclass(Feature, ABC)
        
        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            Feature()
    
    def test_feature_abstract_methods(self):
        """Test that Feature has required abstract methods"""
        abstract_methods = Feature.__abstractmethods__
        
        expected_methods = {
            'get_tools',
            'get_resources', 
            'handle_tool_call',
            'handle_resource_request'
        }
        
        assert abstract_methods == expected_methods
    
    def test_concrete_feature_implementation(self):
        """Test that concrete implementation works"""
        
        class ConcreteFeature(Feature):
            def get_tools(self):
                return []
            
            def get_resources(self):
                return []
            
            async def handle_tool_call(self, name, arguments):
                return f"Tool: {name}"
            
            async def handle_resource_request(self, uri):
                return f"Resource: {uri}"
        
        # Should be able to instantiate concrete implementation
        feature = ConcreteFeature()
        assert isinstance(feature, Feature)
        
        # Test methods work
        assert feature.get_tools() == []
        assert feature.get_resources() == []