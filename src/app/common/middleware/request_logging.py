"""Request diagnostics without clinical bodies, credentials or URL query values."""
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ..logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_size=10000):
        super().__init__(app)
        # Retain the constructor contract; bodies are never read for logging.
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        logger.info('Request started', extra={'event':'request_start','request_id':request_id,'method':request.method})
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error('Request failed', extra={'event':'request_failed','request_id':request_id,'error_type':type(exc).__name__})
            raise
        response.headers['x-request-id'] = request_id
        # Route templates cannot contain patient-provided query/header/body content.
        route = request.scope.get('route')
        logger.info('Request complete', extra={'event':'request_complete','request_id':request_id,
            'method':request.method,'route':getattr(route,'path','unmatched'),
            'status_code':response.status_code,'duration_ms':round((time.monotonic()-started)*1000,2)})
        return response
