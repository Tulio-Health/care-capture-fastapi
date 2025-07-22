from fastapi import HTTPException, Request
from .base import HealthCheckError, CareCaptureError

async def health_check_exception_handler(request: Request, exc: HealthCheckError) -> HTTPException:
    """Handler for HealthCheckError exceptions"""
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.detail
    )

async def care_capture_exception_handler(request: Request, exc: CareCaptureError) -> HTTPException:
    """Handler for CareCaptureError exceptions"""
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.detail
    ) 