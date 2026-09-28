"""Background execution for the two heavy summarization endpoints, with a dedicated
concurrency cap and a token-scoped Redis completion signal Node API polls.

See care-capture-nodeapi's `.research/fastapi-async-summary-quickfix/round5-final.md`
section 5 for the full design and the three rounds of red-team hardening behind `_run`'s
exact control flow (fail-fast busy check before acquiring `_bg_slots`, the semaphore
acquisition happening INSIDE the outer try so a cancel while still acquiring is still
caught, and the inline-synchronous cancellation signal). Do not simplify that nesting
without re-reading that section first.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from redis import Redis

from src.app.common.constants.cache_keys import CACHE_KEY_PREFIX
from src.app.core.settings import get_settings, resolve_redis_password
from src.app.services.summary_runtime import model_error_code

logger = logging.getLogger(__name__)

# Strong refs so a spawned task is never garbage-collected mid-flight (a well-known
# asyncio.create_task pitfall); discarded once the task finishes.
_bg_tasks: set[asyncio.Task] = set()

# A SEPARATE semaphore from summary_runtime._slots (capacity 4, shared by six summarization
# services). Background dispatch may hold at most 2 of those 4 admission slots, so the four
# sync-called endpoints (transcript-summarization, fhir-analysis, comprehensive-summary,
# playground-summarization) always have >=2 reachable. Do not touch summary_runtime.py.
_bg_slots = asyncio.Semaphore(2)

_SIGNAL_TTL_SECONDS = 1800

_signal_redis: Optional[Redis] = None


def _get_signal_redis() -> Redis:
    """Lazy singleton: mirrors cache/redis.py's RedisClient.client property so importing
    this module (pulled in by routes/care_capture.py) never connects to Redis or reads
    settings before SSM parameters are loaded."""
    global _signal_redis
    if _signal_redis is None:
        settings = get_settings()
        _signal_redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=resolve_redis_password(settings.REDIS_PASSWORD),
            db=0,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _signal_redis


def _key(appointment_id: Any, source: str, token: str) -> str:
    """Token-scoped completion-signal key (round4 MAJOR-A1 / round5 section 6.1): the
    token lives IN the key, not just the value, so an abandoned earlier attempt's late
    write can never land on the current attempt's key. Byte-exact contract with Node
    API's REDIS_POLL_CLIENT (section 6.2) -- do not paraphrase this format."""
    return f"{CACHE_KEY_PREFIX}:summary:async:done:{appointment_id}:{source}:{token}"


def _payload(status: str, reason_code: Optional[str], token: str) -> str:
    return json.dumps({"status": status, "reason_code": reason_code, "token": token})


async def _signal(
    appointment_id: Any,
    source: str,
    token: str,
    status: str,
    reason_code: Optional[str] = None,
) -> None:
    """Terminal succeeded/failed signal. Loop is live here, so the write is `to_thread`'d
    (round2 MINOR-1) rather than inline. Swallows its own Redis failures so a signal-write
    error is never miscategorized as a `coro_factory` failure by the caller's except block --
    "both outcomes always write" (section 6.2) is best-effort, not a hard guarantee."""
    key = _key(appointment_id, source, token)
    value = _payload(status, reason_code, token)
    try:
        await asyncio.to_thread(
            _get_signal_redis().set, key, value, ex=_SIGNAL_TTL_SECONDS
        )
    except Exception:
        logger.exception(
            "summary_async_signal_write_failed appointment_id=%s source=%s token=%s status=%s",
            appointment_id,
            source,
            token,
            status,
        )
    logger.info(
        "summary_async_signal appointment_id=%s source=%s status=%s reason_code=%s token=%s",
        appointment_id,
        source,
        status,
        reason_code,
        token,
    )


async def _run(
    coro_factory: Callable[[], Awaitable[object]],
    appointment_id: Any,
    source: str,
    token: str,
) -> None:
    """Run `coro_factory()` under the background-only concurrency cap and signal the
    terminal outcome. Structure (round6 MINOR-1 hardened):
      - `_bg_slots.locked()` is checked BEFORE acquiring: a racing 3rd/4th dispatch fails
        fast with SUMMARY_BUSY instead of parking indefinitely behind `async with`.
      - `async with _bg_slots:` sits INSIDE the outer try, so a cancel while still
        acquiring the semaphore still reaches the CancelledError branch below.
      - Success/failure signal writes go through `_signal` (awaited `to_thread` -- the
        loop is live and worth protecting).
      - Cancellation (lifespan shutdown, scale-in) writes an INLINE SYNCHRONOUS Redis SET
        -- never awaited, so uvicorn's final cancellation sweep at loop close cannot
        re-suspend and abandon it -- on its own try/except: pass, then re-raises.
    """
    try:
        if _bg_slots.locked():
            await _signal(appointment_id, source, token, "failed", "SUMMARY_BUSY")
            return
        async with _bg_slots:
            try:
                await coro_factory()
                await _signal(appointment_id, source, token, "succeeded")
            except Exception as exc:
                await _signal(
                    appointment_id, source, token, "failed", model_error_code(exc)
                )
    except asyncio.CancelledError:
        try:
            _get_signal_redis().set(
                _key(appointment_id, source, token),
                _payload("failed", "SUMMARY_TASK_CANCELLED", token),
                ex=_SIGNAL_TTL_SECONDS,
            )
        except Exception:
            pass
        raise


def dispatch(
    coro_factory: Callable[[], Awaitable[object]],
    appointment_id: Any,
    source: str,
    token: str,
) -> "asyncio.Task[None]":
    """Spawn `_run` as an independent `asyncio.create_task` (NOT Starlette
    `BackgroundTasks` -- see routes/care_capture.py) and hold a strong reference in
    `_bg_tasks` until it finishes."""
    task = asyncio.create_task(_run(coro_factory, appointment_id, source, token))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task
