class QuickBuildError(Exception):
    """Base exception for QuickBuild API errors"""
    
    def __init__(self, message: str, error_code: str, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)

class AuthenticationError(QuickBuildError):
    """Authentication failed with QuickBuild"""
    pass

class ResourceNotFoundError(QuickBuildError):
    """Requested resource not found"""
    pass

class QuickBuildServerError(QuickBuildError):
    """QuickBuild server error"""
    pass

class QuickBuildUnavailableError(QuickBuildError):
    """QuickBuild server unavailable"""
    pass

# Error mapping for common HTTP status codes
ERROR_MAPPINGS = {
    401: "AUTHENTICATION_FAILED",
    404: "RESOURCE_NOT_FOUND", 
    500: "QUICKBUILD_SERVER_ERROR",
    "CONNECTION_ERROR": "QUICKBUILD_UNAVAILABLE"
}