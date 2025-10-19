from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_serializer
from enum import Enum
from uuid import UUID


class ErrorType(str, Enum):
    """Types of errors that can occur in the API"""
    VALIDATION_ERROR = "validation_error"
    BUSINESS_LOGIC_ERROR = "business_logic_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND_ERROR = "not_found_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    INTERNAL_ERROR = "internal_error"


class ValidationErrorDetail(BaseModel):
    """Detailed information about a specific validation error"""
    field: str
    message: str
    invalid_value: Optional[Any] = None
    expected_type: Optional[str] = None
    
    @field_serializer('invalid_value')
    def serialize_invalid_value(self, value):
        """Custom serializer for invalid_value field"""
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, dict):
            # Handle nested dictionaries with UUIDs
            return {k: str(v) if isinstance(v, UUID) else v for k, v in value.items()}
        return value


class APIErrorResponse(BaseModel):
    """Standardized error response model"""
    error: bool = True
    error_type: ErrorType
    message: str
    details: Optional[str] = None
    validation_errors: Optional[List[ValidationErrorDetail]] = None
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None


class BusinessLogicError(Exception):
    """Custom exception for business logic errors"""
    def __init__(self, message: str, details: Optional[str] = None, error_code: Optional[str] = None):
        self.message = message
        self.details = details
        self.error_code = error_code
        super().__init__(self.message)


class ExternalServiceError(Exception):
    """Custom exception for external service errors"""
    def __init__(self, service: str, message: str, details: Optional[str] = None):
        self.service = service
        self.message = message
        self.details = details
        super().__init__(f"{service}: {message}")