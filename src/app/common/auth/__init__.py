"""
Authentication utilities for FastAPI routes
"""
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status


def get_authenticated_user(request: Request) -> Dict[str, Any]:
    """
    Get the authenticated user from the request state.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        Dictionary containing user information
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not hasattr(request.state, 'user'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    user = request.state.user
    
    # Validate user object
    if not user or not user.get('clerk_id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication state"
        )
    
    return user


def get_user_id(request: Request) -> str:
    """
    Get the authenticated user's Clerk ID.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The user's Clerk ID
    """
    user = get_authenticated_user(request)
    return user['clerk_id']


def get_user_email(request: Request) -> Optional[str]:
    """
    Get the authenticated user's email.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The user's email or None
    """
    user = get_authenticated_user(request)
    return user.get('email')


def get_user_role(request: Request) -> str:
    """
    Get the authenticated user's role.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The user's role (default: 'primary')
    """
    user = get_authenticated_user(request)
    return user.get('role', 'primary')


def is_authenticated(request: Request) -> bool:
    """
    Check if the request has an authenticated user.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        True if user is authenticated, False otherwise
    """
    if not hasattr(request.state, 'user'):
        return False
    
    user = request.state.user
    return bool(user and user.get('is_authenticated', False))


__all__ = [
    'get_authenticated_user',
    'get_user_id',
    'get_user_email',
    'get_user_role',
    'is_authenticated'
]