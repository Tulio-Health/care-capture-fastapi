import traceback
import json
from datetime import datetime
from typing import Union, Dict, Any
from uuid import UUID
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.responses import JSONResponse

from .error_models import (
    APIErrorResponse, 
    ErrorType, 
    ValidationErrorDetail, 
    BusinessLogicError, 
    ExternalServiceError
)
from .logging import get_logger

logger = get_logger(__name__)


def serialize_for_json(obj):
    """Convert objects to JSON-serializable format"""
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        # Recursively serialize dictionary values
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        # Recursively serialize list/tuple items
        return [serialize_for_json(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return str(obj)
    else:
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)


def create_validation_error_response(
    exc: Union[RequestValidationError, ValidationError],
    request: Request,
    request_id: str = None
) -> JSONResponse:
    """Create a detailed validation error response"""
    
    validation_errors = []
    
    # Handle FastAPI RequestValidationError
    if isinstance(exc, RequestValidationError):
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"][1:])  # Skip 'body' prefix
            invalid_value = error.get("input")
            # Serialize complex objects for JSON
            if invalid_value is not None:
                try:
                    json.dumps(invalid_value)
                except (TypeError, ValueError):
                    invalid_value = serialize_for_json(invalid_value)
            
            validation_errors.append(ValidationErrorDetail(
                field=field,
                message=error["msg"],
                invalid_value=invalid_value,
                expected_type=error.get("type")
            ))
    
    # Handle Pydantic ValidationError
    elif isinstance(exc, ValidationError):
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            invalid_value = error.get("input")
            # Serialize complex objects for JSON
            if invalid_value is not None:
                try:
                    json.dumps(invalid_value)
                except (TypeError, ValueError):
                    invalid_value = serialize_for_json(invalid_value)
            
            validation_errors.append(ValidationErrorDetail(
                field=field,
                message=error["msg"],
                invalid_value=invalid_value,
                expected_type=error.get("type")
            ))
    
    error_response = APIErrorResponse(
        error_type=ErrorType.VALIDATION_ERROR,
        message="Request validation failed",
        details=f"Found {len(validation_errors)} validation error(s)",
        validation_errors=validation_errors,
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
        method=request.method
    )
    
    logger.warning(f"Validation error on {request.method} {request.url.path}: {validation_errors}")
    
    try:
        content = error_response.model_dump(exclude_none=True)
        return JSONResponse(
            status_code=422,
            content=content
        )
    except Exception as e:
        logger.error(f"Error serializing validation error response: {str(e)}")
        # Fallback error response
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "error_type": "validation_error",
                "message": "Request validation failed",
                "details": str(exc),
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )


def create_business_logic_error_response(
    exc: BusinessLogicError,
    request: Request,
    request_id: str = None
) -> JSONResponse:
    """Create a business logic error response"""
    
    error_response = APIErrorResponse(
        error_type=ErrorType.BUSINESS_LOGIC_ERROR,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
        method=request.method
    )
    
    logger.warning(f"Business logic error on {request.method} {request.url.path}: {exc.message}")
    
    return JSONResponse(
        status_code=400,
        content=error_response.model_dump(exclude_none=True)
    )


def create_external_service_error_response(
    exc: ExternalServiceError,
    request: Request,
    request_id: str = None
) -> JSONResponse:
    """Create an external service error response"""
    
    error_response = APIErrorResponse(
        error_type=ErrorType.EXTERNAL_SERVICE_ERROR,
        message=f"External service error: {exc.service}",
        details=exc.details or exc.message,
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
        method=request.method
    )
    
    logger.error(f"External service error on {request.method} {request.url.path}: {exc.service} - {exc.message}")
    
    return JSONResponse(
        status_code=503,
        content=error_response.model_dump(exclude_none=True)
    )


def create_http_error_response(
    exc: HTTPException,
    request: Request,
    request_id: str = None
) -> JSONResponse:
    """Create a standardized HTTP error response"""
    
    # Determine error type based on status code
    error_type_mapping = {
        401: ErrorType.AUTHENTICATION_ERROR,
        403: ErrorType.AUTHORIZATION_ERROR,
        404: ErrorType.NOT_FOUND_ERROR,
        429: ErrorType.RATE_LIMIT_ERROR,
    }
    
    error_type = error_type_mapping.get(exc.status_code, ErrorType.INTERNAL_ERROR)
    
    error_response = APIErrorResponse(
        error_type=error_type,
        message=str(exc.detail),
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
        method=request.method
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True)
    )


def create_internal_error_response(
    exc: Exception,
    request: Request,
    request_id: str = None
) -> JSONResponse:
    """Create an internal server error response"""
    
    error_response = APIErrorResponse(
        error_type=ErrorType.INTERNAL_ERROR,
        message="An internal error occurred",
        details="Please contact support if this error persists",
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
        method=request.method
    )
    
    logger.error(
        f"Internal error on {request.method} {request.url.path}: {str(exc)}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(exclude_none=True)
    )


def extract_request_id(request: Request) -> str:
    """Extract request ID from request headers or generate one"""
    # Try to get request ID from headers (if set by middleware)
    request_id = request.headers.get("x-request-id")
    if not request_id and hasattr(request.state, "request_id"):
        request_id = request.state.request_id
    return request_id