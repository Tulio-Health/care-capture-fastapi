"""
Test endpoint to verify Clerk authentication middleware
"""
from fastapi import APIRouter, Request
from typing import Dict, Any
from ..common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
)

@router.get("/test")
async def test_authentication(request: Request) -> Dict[str, Any]:
    """
    Test endpoint to verify Clerk JWT authentication is working.
    This endpoint will be protected by the ClerkAuthMiddleware automatically.
    
    Returns user information if authenticated, otherwise returns 401.
    """
    # The middleware has already validated the JWT and attached user info to request.state
    if hasattr(request.state, 'user'):
        user = request.state.user
        logger.info(f"✅ Authentication test successful - User ID: {user.get('clerk_id')}, Role: {user.get('role')}")
        
        return {
            "status": "authenticated",
            "user_id": user.get('clerk_id'),
            "email": user.get('email'),
            "role": user.get('role'),
            "session_id": user.get('session_id'),
            "message": "JWT authentication successful"
        }
    else:
        # This shouldn't happen if middleware is working correctly
        return {
            "status": "unauthenticated",
            "message": "No user information found"
        }