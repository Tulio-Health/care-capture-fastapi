"""Test for the Regime A deferred audit-replay loop parallelization (topic-D
parallelize-and-sizing, Change 3, `_verify_final`'s `for stage, evidence, output in audits`
loop -> `asyncio.gather`). Each `verify_grounding` call reads only its own `(evidence, output)`
pair, so nothing is shared across audits. This proves the `accepted_ids` filter still drops
exactly the right audits before the survivors run (now concurrently), and that a failing audit
still propagates.
"""
import asyncio
from types import SimpleNamespace as NS

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.services.document_extraction import DocumentProcessingError

# Large enough that `_verify_final`'s single deferred-audit attempt is skipped outright (over
# GROUNDING_SANITY_MAX_CHARACTERS, section 4.4(c)'s pinned malformed-input bound -- the same
# bound grounding_request_fits checks first, on every path), landing straight in the
# replay-loop fallback path this test targets.
_HUGE_SOURCE = "x" * 200_000
_CANDIDATE = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})


@pytest.mark.asyncio
async def test_audit_replay_loop_filters_and_parallelizes_surviving_audits(monkeypatch):
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()

    output_a = NS(source_document_id="doc-a")
    output_b = NS(source_document_id="doc-b")
    output_c = NS(source_document_id="doc-c")
    audits = [
        ("extraction", "evidence-a", output_a),
        ("extraction", "evidence-b", output_b),  # doc-b not in accepted_ids -> filtered out
        ("synthesis", "evidence-c", output_c),   # non-extraction stage -> always survives
    ]

    seen_calls = []
    in_flight = 0
    max_in_flight = 0

    async def fake_verify_grounding(model, evidence, output):
        nonlocal in_flight, max_in_flight
        seen_calls.append(evidence)
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1

    monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)

    token = chain._deferred_grounding.set(audits)
    try:
        await chain_instance._verify_final(_HUGE_SOURCE, _CANDIDATE, accepted_ids={"doc-a"})
    finally:
        chain._deferred_grounding.reset(token)

    assert sorted(seen_calls) == ["evidence-a", "evidence-c"]
    assert max_in_flight > 1  # the two surviving audits actually overlapped


@pytest.mark.asyncio
async def test_audit_replay_loop_still_propagates_a_failing_audit(monkeypatch):
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()

    output_a = NS(source_document_id="doc-a")
    audits = [("extraction", "evidence-a", output_a)]

    async def failing_verify_grounding(model, evidence, output):
        raise DocumentProcessingError("CLINICAL_EVIDENCE_FAILED")

    monkeypatch.setattr(chain, "verify_grounding", failing_verify_grounding)

    token = chain._deferred_grounding.set(audits)
    try:
        with pytest.raises(DocumentProcessingError) as excinfo:
            await chain_instance._verify_final(_HUGE_SOURCE, _CANDIDATE, accepted_ids={"doc-a"})
        assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"
    finally:
        chain._deferred_grounding.reset(token)
