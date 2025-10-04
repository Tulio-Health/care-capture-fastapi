import time
import json
import uuid
from typing import Callable, Dict, Any
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message

from ..logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log detailed request and response information for debugging.
    
    Features:
    - Logs request method, URL, headers, query params, and body
    - Logs response status, headers, and body
    - Adds unique request ID for tracing
    - Measures request duration
    - Handles different content types appropriately
    - Sanitizes sensitive information
    """
    
    def __init__(self, app, max_body_size: int = 10000):
        super().__init__(app)
        self.max_body_size = max_body_size
        self.sensitive_headers = {
            'authorization', 'cookie', 'x-api-key', 'x-auth-token'
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Store request ID in request state for access by error handlers
        request.state.request_id = request_id
        
        # Record start time
        start_time = time.time()
        
        # Log request details
        await self._log_request(request, request_id)
        
        # Process request and capture response
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers["x-request-id"] = request_id
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log response details
        await self._log_response(request, response, request_id, duration)
        
        return response
    
    async def _log_request(self, request: Request, request_id: str):
        """Log detailed request information"""
        try:
            # Basic request info
            method = request.method
            url = str(request.url)
            client_ip = self._get_client_ip(request)
            
            # Headers (sanitized)
            headers = self._sanitize_headers(dict(request.headers))
            
            # Query parameters
            query_params = dict(request.query_params) if request.query_params else {}
            
            # Path parameters
            path_params = dict(request.path_params) if hasattr(request, 'path_params') else {}
            
            # Request body (if present and not too large)
            body_info = await self._get_request_body_info(request)
            
            log_data = {
                "event": "request_start",
                "request_id": request_id,
                "method": method,
                "url": url,
                "client_ip": client_ip,
                "path_params": path_params,
                "query_params": query_params,
                "headers": headers,
                **body_info
            }
            
            logger.info(f"[{request_id}] {method} {url} - Request started", extra=log_data)
            
            # Log detailed body for debugging if it's small enough
            if body_info.get("body_content") and len(str(body_info["body_content"])) < 1000:
                logger.debug(f"[{request_id}] Request body: {body_info['body_content']}")
            
        except Exception as e:
            logger.error(f"[{request_id}] Error logging request: {str(e)}")
    
    async def _log_response(self, request: Request, response: Response, request_id: str, duration: float):
        """Log detailed response information"""
        try:
            method = request.method
            url = str(request.url)
            status_code = response.status_code
            
            # Response headers (sanitized)
            response_headers = self._sanitize_headers(dict(response.headers))
            
            # Response body (if accessible and not too large)
            body_info = await self._get_response_body_info(response)
            
            log_data = {
                "event": "request_complete",
                "request_id": request_id,
                "method": method,
                "url": url,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
                "response_headers": response_headers,
                **body_info
            }
            
            # Choose log level based on status code
            if status_code >= 500:
                log_level = "error"
            elif status_code >= 400:
                log_level = "warning"
            else:
                log_level = "info"
            
            getattr(logger, log_level)(
                f"[{request_id}] {method} {url} - {status_code} ({duration*1000:.1f}ms)",
                extra=log_data
            )
            
            # Log response body for error cases
            if status_code >= 400 and body_info.get("body_content"):
                logger.warning(f"[{request_id}] Error response body: {body_info['body_content']}")
            
        except Exception as e:
            logger.error(f"[{request_id}] Error logging response: {str(e)}")
    
    async def _get_request_body_info(self, request: Request) -> Dict[str, Any]:
        """Extract request body information safely"""
        try:
            content_type = request.headers.get("content-type", "").lower()
            content_length = request.headers.get("content-length")
            
            body_info = {
                "content_type": content_type,
                "content_length": content_length
            }
            
            # Skip body reading for certain content types or large payloads
            if content_length and int(content_length) > self.max_body_size:
                body_info["body_truncated"] = f"Body too large ({content_length} bytes)"
                return body_info
            
            if "multipart/" in content_type or "application/octet-stream" in content_type:
                body_info["body_content"] = "[Binary content]"
                return body_info
            
            # Read body for JSON/text content
            if content_type and ("json" in content_type or "text" in content_type or "xml" in content_type):
                body = await request.body()
                if body:
                    try:
                        if "json" in content_type:
                            body_info["body_content"] = json.loads(body.decode())
                        else:
                            body_content = body.decode()[:self.max_body_size]
                            body_info["body_content"] = body_content
                            if len(body) > self.max_body_size:
                                body_info["body_truncated"] = True
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        body_info["body_error"] = f"Failed to parse body: {str(e)}"
                        body_info["body_content"] = "[Unparseable content]"
            
            return body_info
            
        except Exception as e:
            return {"body_error": f"Error reading request body: {str(e)}"}
    
    async def _get_response_body_info(self, response: Response) -> Dict[str, Any]:
        """Extract response body information safely"""
        try:
            body_info = {}
            
            # Skip for streaming responses
            if isinstance(response, StreamingResponse):
                body_info["body_content"] = "[Streaming response]"
                return body_info
            
            # Try to get response body
            if hasattr(response, 'body') and response.body:
                try:
                    content_type = response.headers.get("content-type", "").lower()
                    
                    if len(response.body) > self.max_body_size:
                        body_info["body_truncated"] = f"Response too large ({len(response.body)} bytes)"
                        return body_info
                    
                    if "json" in content_type:
                        body_info["body_content"] = json.loads(response.body.decode())
                    elif "text" in content_type or "xml" in content_type:
                        body_info["body_content"] = response.body.decode()
                    else:
                        body_info["body_content"] = "[Binary content]"
                        
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    body_info["body_error"] = f"Failed to parse response body: {str(e)}"
                    body_info["body_content"] = "[Unparseable content]"
            
            return body_info
            
        except Exception as e:
            return {"body_error": f"Error reading response body: {str(e)}"}
    
    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove or mask sensitive header values"""
        sanitized = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in self.sensitive_headers:
                sanitized[key] = "[REDACTED]"
            elif key_lower == 'user-agent':
                # Truncate user-agent for brevity
                sanitized[key] = value[:100] + "..." if len(value) > 100 else value
            else:
                sanitized[key] = value
        return sanitized
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers first (for proxies/load balancers)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client
        if hasattr(request, 'client') and request.client:
            return request.client.host
        
        return "unknown"