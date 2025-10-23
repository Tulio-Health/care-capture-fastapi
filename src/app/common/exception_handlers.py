from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .error_handlers import (
    create_validation_error_response,
    create_business_logic_error_response,
    create_external_service_error_response,
    create_http_error_response,
    create_internal_error_response,
    extract_request_id
)
from .error_models import BusinessLogicError, ExternalServiceError
from .logging import get_logger

logger = get_logger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    request_id = extract_request_id(request)
    return create_validation_error_response(exc, request, request_id)


async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors"""
    request_id = extract_request_id(request)
    return create_validation_error_response(exc, request, request_id)


async def business_logic_exception_handler(request: Request, exc: BusinessLogicError):
    """Handle business logic errors"""
    request_id = extract_request_id(request)
    return create_business_logic_error_response(exc, request, request_id)


async def external_service_exception_handler(request: Request, exc: ExternalServiceError):
    """Handle external service errors"""
    request_id = extract_request_id(request)
    return create_external_service_error_response(exc, request, request_id)


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    request_id = extract_request_id(request)
    return create_http_error_response(exc, request, request_id)


async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    request_id = extract_request_id(request)
    return create_internal_error_response(exc, request, request_id)


def register_exception_handlers(app: FastAPI):
    """Register all exception handlers with the FastAPI app"""
    
    # Validation errors (422)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    
    # Business logic errors (400)
    app.add_exception_handler(BusinessLogicError, business_logic_exception_handler)
    
    # External service errors (503)
    app.add_exception_handler(ExternalServiceError, external_service_exception_handler)
    
    # HTTP errors (401, 403, 404, etc.)
    app.add_exception_handler(HTTPException, http_exception_handler)
    
    # Catch-all for unexpected errors (500)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Exception handlers registered successfully")