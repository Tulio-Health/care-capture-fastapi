from fastapi import APIRouter
from typing import Dict, Any
from ..version import API_VERSION
import time

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

# Track start time for uptime calculation
start_time = time.time()

@router.get("",
    response_model=Dict[str, Any],
    summary="Health check endpoint",
    description="Endpoint to check the health status of the API service",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2024-10-22T21:45:00.000Z",
                        "uptime": 3600.0,
                        "version": "1.0.0-local",
                        "build": "local"
                    }
                }
            }
        }
    }
)
async def health_check():
    from datetime import datetime
    current_time = time.time()
    uptime = current_time - start_time
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime": uptime,
        "version": API_VERSION["version"],
        "build": API_VERSION["buildNumber"]
    } 