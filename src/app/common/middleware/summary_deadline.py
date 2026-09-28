"""Bound the entire summary request, including dependency and authentication waits."""
import asyncio
import time
from starlette.responses import JSONResponse
from src.app.services.summary_runtime import request_started


class SummaryDeadlineMiddleware:
    # 305 was above App Runner's hard 120s request cap and could never fire in
    # production (see .research/fastapi-deadline-and-retry-architecture/findings.md).
    # 115 is a real backstop: above bounded_summary's ~110s job deadline (so the
    # legible SUMMARY_DEADLINE_EXCEEDED path wins first) but still inside the
    # platform's 120s window.
    def __init__(self, app, timeout_seconds=115):
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
