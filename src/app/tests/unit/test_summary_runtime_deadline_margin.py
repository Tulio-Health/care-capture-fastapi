"""bounded_summary's deadline fallback used to be hardcoded to 120 -- exactly AWS App
Runner's hard, unconfigurable 120s HTTP request cap, a zero-margin race (see
.research/fastapi-deadline-and-retry-architecture/findings.md). It is now 110, giving a
real ~10s margin so a stuck job self-aborts with a legible SUMMARY_DEADLINE_EXCEEDED
before the platform kills the connection.

These tests exercise the real `bounded_summary` decorator (not a reimplementation of its
formula) end to end, mirroring test_summary_runtime_budget_observability.py's pattern.
"""
import time
from types import SimpleNamespace as NS

import pytest

from src.app.services import summary_runtime as sr


class _Service:
    @sr.bounded_summary
    async def run(self, request):
        return sr._current_budget.get().deadline


@pytest.mark.asyncio
async def test_deadline_falls_back_to_110_when_timeout_seconds_is_entirely_absent():
    request = NS()  # no timeout_seconds attribute at all -- the true fallback path
    started = time.monotonic()
    deadline = await _Service().run(request)
    assert abs((deadline - started) - 110) < 1.0


@pytest.mark.asyncio
async def test_deadline_honors_an_explicitly_sent_110_value():
    request = NS(timeout_seconds=110)
    started = time.monotonic()
    deadline = await _Service().run(request)
    assert abs((deadline - started) - 110) < 1.0


@pytest.mark.asyncio
async def test_deadline_still_caps_an_oversized_explicit_value_at_300():
    request = NS(timeout_seconds=1000)
    started = time.monotonic()
    deadline = await _Service().run(request)
    assert abs((deadline - started) - 300) < 1.0
