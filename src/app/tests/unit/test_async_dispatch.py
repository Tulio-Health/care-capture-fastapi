"""Unit tests for src.app.services.async_dispatch (round5-final.md, care-capture-nodeapi
sibling repo, section 5 + section 10's fastapi test list):

  1. dispatch() spawns a real asyncio.Task and _run signals `succeeded` on the correct
     token-scoped key on success.
  2. A coro_factory that raises signals `failed` with the classified reason_code.
  3. A 3rd concurrent dispatch while 2 are in flight gets an immediate SUMMARY_BUSY
     (the task's own fail-fast check, per round6 MINOR-1).
  4. Cancellation during an ACTUAL lifespan-shutdown drain (shutdown_summary_work, the
     real function application.py's lifespan calls) writes SUMMARY_TASK_CANCELLED -- a
     bare task.cancel() on a still-live loop does not exercise the same path and is not
     an acceptable substitute (round4 MAJOR-A2).
  5. A dispatched task outlives its own "request" await boundary, proving
     asyncio.create_task (not Starlette BackgroundTasks) is what's spawning it.
"""

import asyncio
import json
from typing import Generator

import pytest

from src.app.services import async_dispatch
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summary_runtime import bounded_summary, shutdown_summary_work

pytestmark = pytest.mark.asyncio


class _FakeSignalRedis:
    """Records every `.set(...)` call. Calls in these tests never arrive concurrently
    from multiple threads at once, so no locking is needed."""

    def __init__(self):
        self.calls = []

    def set(self, key, value, ex=None):
        self.calls.append((key, value, ex))
        return True


@pytest.fixture(autouse=True)
def fake_signal_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeSignalRedis:
    fake = _FakeSignalRedis()
    monkeypatch.setattr(async_dispatch, "_get_signal_redis", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def reset_bg_slots() -> Generator[None, None, None]:
    """_bg_slots is module-level state shared across the whole test session; give every
    test a fresh, fully-available Semaphore(2)."""
    async_dispatch._bg_slots = asyncio.Semaphore(2)
    yield


def _last_call(fake):
    key, value, ex = fake.calls[-1]
    return key, json.loads(value), ex


async def test_dispatch_spawns_task_and_signals_succeeded_on_token_scoped_key(
    fake_signal_redis,
) -> None:
    ran = []

    async def coro_factory():
        ran.append(True)

    task = async_dispatch.dispatch(
        coro_factory, "appt-1", "attachment_summary", "tok-1"
    )
    assert task in async_dispatch._bg_tasks
    assert isinstance(task, asyncio.Task)

    await task

    assert ran == [True]
    assert task not in async_dispatch._bg_tasks

    key, value, ex = _last_call(fake_signal_redis)
    assert key == async_dispatch._key("appt-1", "attachment_summary", "tok-1")
    assert value == {"status": "succeeded", "reason_code": None, "token": "tok-1"}
    assert ex == async_dispatch._SIGNAL_TTL_SECONDS


async def test_run_signals_failed_with_classified_reason_code_on_exception(
    fake_signal_redis,
) -> None:
    async def coro_factory():
        raise DocumentProcessingError("MODEL_AUTH_FAILED")

    task = async_dispatch.dispatch(coro_factory, "appt-2", "procedure_summary", "tok-2")
    await task  # _run swallows the exception itself -- the task completes normally

    key, value, _ = _last_call(fake_signal_redis)
    assert key == async_dispatch._key("appt-2", "procedure_summary", "tok-2")
    assert value == {
        "status": "failed",
        "reason_code": "MODEL_AUTH_FAILED",
        "token": "tok-2",
    }


async def test_third_concurrent_dispatch_gets_immediate_summary_busy(
    fake_signal_redis,
) -> None:
    gate1 = asyncio.Event()
    gate2 = asyncio.Event()

    async def _slow(gate):
        await gate.wait()

    task1 = async_dispatch.dispatch(
        lambda: _slow(gate1), "a1", "attachment_summary", "t1"
    )
    task2 = async_dispatch.dispatch(
        lambda: _slow(gate2), "a2", "attachment_summary", "t2"
    )

    # Let both scheduled tasks run their first step (acquire _bg_slots, then suspend on
    # their gate) before the 3rd dispatch races them.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert async_dispatch._bg_slots.locked()

    task3 = async_dispatch.dispatch(
        lambda: _slow(asyncio.Event()), "a3", "attachment_summary", "t3"
    )
    await task3  # fails fast -- never touches its own gate

    key, value, _ = _last_call(fake_signal_redis)
    assert key == async_dispatch._key("a3", "attachment_summary", "t3")
    assert value == {"status": "failed", "reason_code": "SUMMARY_BUSY", "token": "t3"}

    gate1.set()
    gate2.set()
    await task1
    await task2


async def test_cancellation_during_actual_lifespan_shutdown_writes_task_cancelled(
    fake_signal_redis,
) -> None:
    """Exercises the REAL drain path application.py's lifespan teardown uses
    (`shutdown_summary_work(timeout=5)`), not a bare `task.cancel()` on a still-live loop
    -- section 10 is explicit that the trivial version proves nothing."""
    started = asyncio.Event()
    release = asyncio.Event()

    class _Req:
        timeout_seconds = 300

    @bounded_summary
    async def _slow_summary(self, request):
        started.set()
        await release.wait()  # would hang forever if never cancelled

    async def coro_factory():
        await _slow_summary(None, _Req())

    task = async_dispatch.dispatch(
        coro_factory, "appt-3", "attachment_summary", "tok-3"
    )
    await started.wait()

    drained = await shutdown_summary_work(timeout=5)
    assert drained is True

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()

    key, value, _ = _last_call(fake_signal_redis)
    assert key == async_dispatch._key("appt-3", "attachment_summary", "tok-3")
    assert value == {
        "status": "failed",
        "reason_code": "SUMMARY_TASK_CANCELLED",
        "token": "tok-3",
    }


async def test_dispatched_task_outlives_its_own_request_response_cycle(
    fake_signal_redis,
) -> None:
    """Proves asyncio.create_task (not Starlette BackgroundTasks, which would be torn
    down with the request): the task is still running after the stand-in "202 response"
    below has already returned."""
    release = asyncio.Event()
    completed = []

    async def coro_factory():
        await release.wait()
        completed.append(True)

    async def handle_request():
        task = async_dispatch.dispatch(
            coro_factory, "appt-4", "attachment_summary", "tok-4"
        )
        return {"accepted": True}, task

    response, task = await handle_request()

    assert response == {"accepted": True}
    assert not task.done()
    assert (
        completed == []
    )  # request already "returned"; background work still in flight

    release.set()
    await task
    assert completed == [True]
