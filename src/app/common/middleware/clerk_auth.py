"""
Clerk JWT Authentication Middleware for FastAPI
"""
import os
import json
import time
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    InvalidSignatureError,
    DecodeError,
    InvalidKeyError,
    InvalidAlgorithmError
)
from ..logging import get_logger

logger = get_logger(__name__)


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for validating Clerk JWT tokens on all API endpoints.
    
    This middleware:
    1. Extracts the Clerk JWT token from request headers (x-clerk-jwt)
    2. Verifies the token using Clerk's public JWT key
    3. Validates token expiration and signature
    4. Extracts user information (user_id, email, role) from the token
    5. Attaches user data to the request state for downstream use
    6. Provides proper error messages for different failure scenarios
    """
    
    # Paths that don't require authentication
    EXCLUDED_PATHS = {
        "/",
        "/health",
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
        "/favicon.ico",
        "/robots.txt",
        "/care-capture/playground-summarization",
    }
    
    # Paths patterns that should be excluded (prefix matching)
    EXCLUDED_PATH_PREFIXES = [
        "/health/",
        "/api/health/",
        "/_health",
    ]
    
    # Valid user roles
    VALID_ROLES = ["primary", "caregiver", "admin", "provider"]
    
    def __init__(self, app: ASGIApp):
        """
        Initialize the Clerk authentication middleware.
        
        Args:
            app: The ASGI application
        """
        super().__init__(app)
        self.public_jwt_key = None
        self.auth_enabled = False
        self._initialize_jwt_key()
    
    def _initialize_jwt_key(self) -> None:
        """
        Initialize and validate the Clerk public JWT key from environment.
        Handles both PEM format and JSON-wrapped keys.
        """
        raw_key = os.getenv('CLERK_PUBLIC_JWT_KEY', '').strip()
        
        if not raw_key:
            logger.warning("⚠️ CLERK_PUBLIC_JWT_KEY not configured - authentication will be disabled")
            logger.warning("To enable authentication, set CLERK_PUBLIC_JWT_KEY in environment or SSM")
            return
        
        try:
            # Check if the key is JSON-wrapped (common in SSM storage)
            if raw_key.startswith('{'):
                try:
                    key_data = json.loads(raw_key)
                    jwt_key = key_data.get('key', raw_key)
                    logger.debug("Extracted JWT key from JSON wrapper")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JWT key JSON: {e}")
                    return
            else:
                jwt_key = raw_key
            
            # Handle different JWT key formats
            if jwt_key.startswith('-----BEGIN'):
                # Already in PEM format
                jwt_key = jwt_key.replace('\\n', '\n')
            elif len(jwt_key) > 200 and not jwt_key.startswith('-----BEGIN'):
                # Raw RSA public key - convert to PEM format
                jwt_key = f"-----BEGIN PUBLIC KEY-----\n{jwt_key}\n-----END PUBLIC KEY-----"
                logger.debug("Converted raw RSA key to PEM format")
            else:
                logger.error(f"Invalid JWT key format - expected PEM or raw RSA key, got: {jwt_key[:50]}...")
                return
            
            self.public_jwt_key = jwt_key
            self.auth_enabled = True
            
            logger.info("✅ Clerk JWT authentication middleware initialized successfully")
            logger.debug(f"JWT key loaded (first 50 chars): {jwt_key[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to initialize JWT key: {e}")
            logger.exception("JWT key initialization error details:")
    
    def _should_skip_auth(self, path: str) -> bool:
        """
        Check if authentication should be skipped for the given path.
        
        Args:
            path: The request path
            
        Returns:
            True if authentication should be skipped
        """
        # Check exact path matches
        if path in self.EXCLUDED_PATHS:
            return True
        
        # Check prefix matches
        for prefix in self.EXCLUDED_PATH_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False
    
    def _generate_request_id(self) -> str:
        """
        Generate a unique request ID for tracking.
        
        Returns:
            A unique request identifier
        """
        import random
        import string
        timestamp = str(int(time.time() * 1000))[-6:]
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{timestamp}-{random_str}"
    
    def _validate_user_role(self, role: Optional[str]) -> str:
        """
        Validate and normalize the user role.
        
        Args:
            role: The role from request headers
            
        Returns:
            Valid role or default 'primary'
        """
        if not role:
            return "primary"
        
        role_lower = role.lower().strip()
        if role_lower in self.VALID_ROLES:
            return role_lower
        
        logger.warning(f"Invalid user role provided: {role}, defaulting to 'primary'")
        return "primary"
    
    def _create_error_response(
        self, 
        status_code: int, 
        error: str, 
        message: str, 
        request_id: str,
        details: Optional[Dict] = None
    ) -> JSONResponse:
        """
        Create a standardized error response.
        
        Args:
            status_code: HTTP status code
            error: Error type
            message: Human-readable error message
            request_id: Request tracking ID
            details: Optional additional error details
            
        Returns:
            JSONResponse with error information
        """
        content = {
            "error": error,
            "message": message,
            "request_id": request_id,
            "timestamp": int(time.time())
        }
        
        if details:
            content["details"] = details
        
        return JSONResponse(
            status_code=status_code,
            content=content
        )
    
    async def dispatch(self, request: Request, call_next):
        """
        Process each request to validate Clerk JWT tokens.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler
            
        Returns:
            Response from the next handler or error response
        """
        # Generate or extract request ID for tracking
        request_id = request.headers.get('x-request-id', self._generate_request_id())
        start_time = time.time()
        
        # Store request ID in request state for downstream use
        request.state.request_id = request_id
        
        # Check if authentication should be skipped
        if self._should_skip_auth(request.url.path):
            logger.debug(f"[{request_id}] Skipping auth for excluded path: {request.url.path}")
            return await call_next(request)
        
        # Skip if authentication is not enabled
        if not self.auth_enabled:
            logger.debug(f"[{request_id}] Auth disabled - proceeding without authentication")
            # Set a default user for development
            request.state.user = {
                "clerk_id": "dev_user",
                "email": "dev@localhost",
                "role": "primary",
                "is_authenticated": False
            }
            return await call_next(request)
        
        try:
            # Extract token and role from headers
            token = request.headers.get("x-clerk-jwt")
            user_role = request.headers.get("x-user-role")
            
            # Log request details
            logger.debug(f"[{request_id}] Auth check - Method: {request.method}, Path: {request.url.path}, "
                        f"IP: {request.client.host if request.client else 'unknown'}")
            
            # Validate token presence
            if not token:
                logger.warning(f"[{request_id}] Missing x-clerk-jwt header for {request.url.path}")
                return self._create_error_response(
                    status.HTTP_401_UNAUTHORIZED,
                    "Unauthorized",
                    "No authentication token provided. Please include x-clerk-jwt header.",
                    request_id
                )
            
            # Verify the JWT token
            try:
                logger.debug(f"[{request_id}] Verifying JWT token (length: {len(token)})")
                
                # Decode and verify the token with Clerk's public key
                decoded_token = jwt.decode(
                    token,
                    self.public_jwt_key,
                    algorithms=["RS256"],
                    options={
                        "verify_signature": True,
                        "verify_exp": True,
                        "verify_nbf": True,
                        "verify_iat": True,
                        "verify_aud": False,  # Clerk doesn't always include audience
                        "require": ["exp", "iat", "sub"]
                    }
                )
                
                # Extract user information from token
                user_id = decoded_token.get('sub')  # Clerk user ID
                email = decoded_token.get('email')
                session_id = decoded_token.get('sid')
                
                # Validate required fields
                if not user_id:
                    logger.error(f"[{request_id}] Token missing 'sub' (user ID) claim")
                    return self._create_error_response(
                        status.HTTP_401_UNAUTHORIZED,
                        "Invalid Token",
                        "Token is missing required user information",
                        request_id
                    )
                
                # Validate and normalize user role
                validated_role = self._validate_user_role(user_role)
                
                # Log successful authentication
                auth_time = int((time.time() - start_time) * 1000)
                logger.info(f"[{request_id}] ✅ Authentication successful - "
                           f"User: {user_id}, Email: {email or 'N/A'}, Role: {validated_role}, "
                           f"Session: {session_id or 'N/A'}, Auth time: {auth_time}ms")
                
                # Attach user info to request state
                request.state.user = {
                    "clerk_id": user_id,
                    "email": email,
                    "role": validated_role,
                    "session_id": session_id,
                    "is_authenticated": True,
                    "token_claims": decoded_token
                }
                
                # Log as requested - print user ID and role
                print(f"Authenticated User - ID: {user_id}, Role: {validated_role}")
                
            except ExpiredSignatureError:
                logger.warning(f"[{request_id}] JWT token expired")
                return self._create_error_response(
                    status.HTTP_401_UNAUTHORIZED,
                    "Token Expired",
                    "Your authentication token has expired. Please sign in again.",
                    request_id
                )
            
            except InvalidSignatureError:
                logger.warning(f"[{request_id}] Invalid JWT signature")
                return self._create_error_response(
                    status.HTTP_401_UNAUTHORIZED,
                    "Invalid Signature",
                    "The token signature is invalid. Please sign in again.",
                    request_id
                )
            
            except DecodeError as e:
                logger.warning(f"[{request_id}] JWT decode error: {str(e)}")
                return self._create_error_response(
                    status.HTTP_401_UNAUTHORIZED,
                    "Invalid Token",
                    "The authentication token could not be decoded.",
                    request_id,
                    {"decode_error": str(e)}
                )
            
            except InvalidKeyError:
                logger.error(f"[{request_id}] Invalid JWT key configuration")
                return self._create_error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "Configuration Error",
                    "Authentication service is misconfigured. Please contact support.",
                    request_id
                )
            
            except InvalidTokenError as e:
                logger.warning(f"[{request_id}] Invalid JWT token: {str(e)}")
                return self._create_error_response(
                    status.HTTP_401_UNAUTHORIZED,
                    "Invalid Token",
                    "The authentication token is invalid.",
                    request_id,
                    {"validation_error": str(e)}
                )
            
            except Exception as e:
                logger.error(f"[{request_id}] Unexpected JWT verification error: {str(e)}")
                logger.exception("JWT verification exception details:")
                return self._create_error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "Authentication Error",
                    "An unexpected error occurred during authentication.",
                    request_id
                )
            
            # Call the next middleware/handler
            response = await call_next(request)
            
            # Log response time
            total_time = int((time.time() - start_time) * 1000)
            logger.debug(f"[{request_id}] Request completed - Status: {response.status_code}, Time: {total_time}ms")
            
            # Add custom headers to response
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Auth-Status"] = "authenticated"
            
            return response
            
        except Exception as e:
            # Catch any unexpected errors
            logger.error(f"[{request_id}] Unexpected error in auth middleware: {str(e)}")
            logger.exception("Middleware exception details:")
            
            return self._create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "An unexpected error occurred. Please try again later.",
                request_id
            )


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Helper function to get the current authenticated user from request.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        User information dictionary or None if not authenticated
    """
    if hasattr(request.state, 'user'):
        return request.state.user
    return None