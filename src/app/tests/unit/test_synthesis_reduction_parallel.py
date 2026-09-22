"""Test for the synthesis hierarchical-reduction group loop parallelization (topic-D
parallelize-and-sizing, Change 2, `_synthesize`'s `groups` loop). `groups` is a disjoint
partition of `records`; each `_synthesize_records` call reads only its own group and returns a
fresh response, so nothing is shared across iterations -- this test proves the new
`asyncio.gather`-based loop (a) actually overlaps multiple group calls concurrently, and (b)
produces an IDENTICAL merged result to the old one-group-at-a-time-in-a-for-loop shape, just
faster.
"""
import asyncio
import json
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest

from src.app.chains.attachment_summarization import chain


@pytest.mark.asyncio
async def test_synthesis_reduction_group_loop_parallelizes_and_preserves_result(monkeypatch):
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()

    # 3 records big enough that the serialized total exceeds _synthesize's 100_000-char
    # single-shot threshold, forcing the group-partition reduction loop to actually run, and
    # small enough individually (well under the 60_000-per-group cap) that the partition logic
    # (unchanged by this PR) puts each in its own group -> 3 groups to run concurrently.
    big_value = "x" * 39_000
    records_input = [{"id": i, "narrative": big_value} for i in range(3)]
    monkeypatch.setattr(chain, "_split_procedures", lambda summaries: records_input)

    state = {"in_flight": 0, "max_in_flight": 0}

    async def fake_synthesize_records(appointment_context, group, count):
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        await asyncio.sleep(0.01)
        state["in_flight"] -= 1
        # Deterministic, shape-agnostic (works for both the raw input records and the
        # already-reduced dicts from a prior level), and genuinely SMALL like a real synthesis
        # response -- a hash of `group`'s content, not the content itself, so `_synthesize`'s
        # own non-shrinking-reduction check (`reduced` must be smaller than `serialized`) passes
        # exactly as it would for a real narrative-condensing model call.
        digest = sha256(json.dumps(group, sort_keys=True, default=str).encode()).hexdigest()
        return NS(model_dump=lambda d=digest: {"summary_of": d})

    monkeypatch.setattr(chain_instance, "_synthesize_records", fake_synthesize_records)

    parallel_response = await chain_instance._synthesize({}, [])

    assert state["max_in_flight"] > 1  # the group loop actually overlapped, not one-at-a-time

    # Old sequential shape (topic-D Change 2's "before"): the exact same grouping logic
    # `_synthesize` still uses (untouched by this PR), but with a plain for-loop instead of
    # `asyncio.gather` around each group's `_synthesize_records` call.
    async def sequential_reference():
        records = records_input
        for _level in range(4):
            serialized = json.dumps(records, ensure_ascii=False, default=str)
            if len(serialized) <= 100_000:
                return await fake_synthesize_records({}, records, len(records))
            groups, current, size = [], [], 0
            for record in records:
                record_size = len(json.dumps(record, ensure_ascii=False, default=str))
                if current and size + record_size > 60_000:
                    groups.append(current)
                    current, size = [], 0
                current.append(record)
                size += record_size
            if current:
                groups.append(current)
            reduced = []
            for group in groups:
                response = await fake_synthesize_records({}, group, len(group))
                reduced.append(response.model_dump())
            records = reduced
        raise AssertionError("sequential reference did not converge within 4 levels")

    sequential_response = await sequential_reference()

    assert parallel_response.model_dump() == sequential_response.model_dump()
