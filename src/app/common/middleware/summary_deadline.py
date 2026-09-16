"""Bound the entire summary request, including dependency and authentication waits."""
import asyncio
import time
from starlette.responses import JSONResponse
from src.app.services.summary_runtime import request_started


class SummaryDeadlineMiddleware:
    def __init__(self, app, timeout_seconds=305):
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not path.startswith('/care-capture/') or not any(word in path for word in ('summar', 'fhir', 'procedure', 'attachment')):
            return await self.app(scope, receive, send)
        started = False
        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)
        token = request_started.set(time.monotonic())
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.app(scope, receive, tracked_send)
        except TimeoutError:
            if not started:
                response = JSONResponse(status_code=503, content={'detail': 'Summarization timed out. Please try again later.'})
                await response(scope, receive, send)
        finally:
            request_started.reset(token)
