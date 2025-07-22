from fastapi import APIRouter
from typing import Dict

router = APIRouter(
    prefix="/health",
    tags=["health"]
)

@router.get("",
    response_model=Dict[str, str],
    summary="Health check endpoint",
    description="Endpoint to check the health status of the API service",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {"status": "healthy"}
                }
            }
        }
    }
)
async def health_check():
    return {"status": "healthy"} 