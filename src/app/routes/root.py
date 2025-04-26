from fastapi import APIRouter
from typing import Dict

router = APIRouter(
    tags=["root"]
)

@router.get("/", 
    response_model=Dict[str, str],
    summary="Root endpoint",
    description="Welcome endpoint that returns a greeting message for the Care Capture AI API"
)
async def root():
    return {"message": "Welcome to Care Capture AI API"} 