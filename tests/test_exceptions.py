"""
Tests for custom exceptions
"""
import pytest

from src.exceptions import (
    QuickBuildError, AuthenticationError, ResourceNotFoundError,
    QuickBuildServerError, QuickBuildUnavailableError, ERROR_MAPPINGS
)


class TestQuickBuildError:
    """Test QuickBuildError base exception"""
    
    def test_basic_error(self):
        """Test basic error creation"""
        error = QuickBuildError("Test error", "TEST_ERROR")
        
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.details == {}
    
    def test_error_with_details(self):
        """Test error with details"""
        details = {"status_code": 500, "endpoint": "/api/test"}
        error = QuickBuildError("Server error", "SERVER_ERROR", details)
        
        assert error.details == details
        assert error.details["status_code"] == 500


class TestSpecificErrors:
    """Test specific error types"""
    
    def test_authentication_error(self):
        """Test authentication error"""
        error = AuthenticationError("Auth failed", "AUTH_ERROR")
        
        assert isinstance(error, QuickBuildError)
        assert error.message == "Auth failed"
        assert error.error_code == "AUTH_ERROR"
    
    def test_resource_not_found_error(self):
        """Test resource not found error"""
        error = ResourceNotFoundError("Not found", "NOT_FOUND")
        
        assert isinstance(error, QuickBuildError)
        assert error.message == "Not found"
    
    def test_server_error(self):
        """Test server error"""
        error = QuickBuildServerError("Server down", "SERVER_DOWN")
        
        assert isinstance(error, QuickBuildError)
        assert error.message == "Server down"
    
    def test_unavailable_error(self):
        """Test unavailable error"""
        error = QuickBuildUnavailableError("Unavailable", "UNAVAILABLE")
        
        assert isinstance(error, QuickBuildError)
        assert error.message == "Unavailable"


class TestErrorMappings:
    """Test error code mappings"""
    
    def test_error_mappings_exist(self):
        """Test that error mappings are defined"""
        assert ERROR_MAPPINGS[401] == "AUTHENTICATION_FAILED"
        assert ERROR_MAPPINGS[404] == "RESOURCE_NOT_FOUND"
        assert ERROR_MAPPINGS[500] == "QUICKBUILD_SERVER_ERROR"
        assert ERROR_MAPPINGS["CONNECTION_ERROR"] == "QUICKBUILD_UNAVAILABLE"
    
    def test_error_mappings_types(self):
        """Test error mapping types"""
        assert isinstance(ERROR_MAPPINGS, dict)
        assert len(ERROR_MAPPINGS) >= 4