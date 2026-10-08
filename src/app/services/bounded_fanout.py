"""Bounded, order-preserving, failure-isolating async fan-out.

``fan_out(items, worker, concurrency=N, deadline_s=D)`` runs ``worker(item)`` for every item with at
most N in flight and returns the results in INPUT ORDER. An item whose worker raised, was cancelled
or had not finished by the deadline yields the ``UNRESOLVED`` sentinel in its slot: a slot is never
omitted and one item's failure never raises out of ``fan_out``.

This bounds the per-request fan-out only. Per-process model concurrency stays owned by
``summary_runtime._model_slots`` (every worker is expected to reach the model through
``model_call``); N should stay at or below that gate.
"""

import asyncio
from typing import Any, Awaitable, Callable, List, Sequence


class _Unresolved:
    """Singleton marker type for a slot whose worker did not produce a result."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNRESOLVED"

    def __bool__(self) -> bool:
        return False


UNRESOLVED = _Unresolved()


async def fan_out(
    items: Sequence[Any],
    worker: Callable[[Any], Awaitable[Any]],
    *,
    concurrency: int,
    deadline_s: float,
) -> List[Any]:
    if (
        isinstance(concurrency, bool)
        or not isinstance(concurrency, int)
        or concurrency < 1
    ):
        raise ValueError("concurrency must be an integer >= 1")
    if not deadline_s or deadline_s <= 0:
        raise ValueError("deadline_s must be > 0")
    out: List[Any] = [UNRESOLVED] * len(items)
    if not items:
        return out
    sem = asyncio.Semaphore(concurrency)

    async def run(index: int, item: Any) -> None:
        async with sem:  # request-level bound
            out[index] = await worker(item)

    tasks = [asyncio.create_task(run(i, item)) for i, item in enumerate(items)]
    try:
        _, pending = await asyncio.wait(tasks, timeout=deadline_s)
        for task in pending:
            task.cancel()
    finally:
        # Reap everything (also when the caller itself is cancelled): no task outlives fan_out.
        for task in tasks:
            if not task.done():
                task.cancel()
        # Exceptions (including CancelledError) are swallowed on purpose; their slot stays UNRESOLVED.
        await asyncio.gather(*tasks, return_exceptions=True)
    return out
