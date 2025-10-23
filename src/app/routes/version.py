"""
Version endpoints for the FastAPI application.
"""
from fastapi import APIRouter
from typing import Dict
from ..version import API_VERSION

router = APIRouter(tags=["version"])

@router.get("/version",
    response_model=Dict[str, str],
    summary="Get API version information",
    description="Returns detailed version information about the API",
    responses={
        200: {
            "description": "Version information",
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0.0-local",
                        "buildNumber": "local",
                        "buildTime": "2024-10-22T21:45:00.000Z",
                        "commit": "local",
                        "branch": "local",
                        "environment": "development"
                    }
                }
            }
        }
    }
)
async def get_version():
    """Get API version information."""
    return API_VERSION

@router.get("/api/version",
    response_model=Dict[str, str],
    summary="Get API version information (alternate path)",
    description="Returns detailed version information about the API",
    responses={
        200: {
            "description": "Version information",
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0.0-local",
                        "buildNumber": "local",
                        "buildTime": "2024-10-22T21:45:00.000Z",
                        "commit": "local",
                        "branch": "local",
                        "environment": "development"
                    }
                }
            }
        }
    }
)
async def get_api_version():
    """Get API version information (alternate path)."""
    return API_VERSION