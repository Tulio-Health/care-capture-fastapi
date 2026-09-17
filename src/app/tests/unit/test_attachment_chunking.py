"""PR-9: chunk sizing (CHUNK_CHAR_LIMIT -> BATCH_CHAR_LIMIT) and the non-mutating
_check_follow_up_grounding wiring into _extract_batch_attempt/_extract_batch.

Cases 1-3 cover chunk sizing (call-count reduction, exhaustiveness, per-chunk size bound).
Case 4 unit-tests _check_follow_up_grounding directly.
Case 5 proves the wiring is reached from _extract_batch_attempt.
Case 6 is the load-bearing test: a hallucinated follow_up quote must still fail the batch
closed, and the shared DocumentSummary object the stub agent returns must be untouched
afterward -- proving the deep-copy discipline in the wiring, not a mutation that would have
silently deleted the bad entry before validate_quotes ever saw it.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import DocumentAttachment, DocumentSummary, FollowUpDetail
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ingestion import mark_parsed


def _doc(text: str, resource_id: str = "doc-1") -> DocumentAttachment:
    """A DocumentAttachment that already satisfies require_parsed (mark_parsed sets the
    sha256/parser_version bookkeeping _create_batches checks)."""
    return mark_parsed(
        DocumentAttachment(
            file_path=f"s3://bucket/{resource_id}.txt",
            content_type="text/plain",
            title="Progress Note",
            extracted_text=text,
            resource_id=resource_id,
        )
    )


def _summary(**overrides) -> DocumentSummary:
    data = dict(
        source_document_id="doc-1",
        evidence_quotes=["Assessment and Plan: continue metformin as directed."],
        source_document_title="Progress Note",
        source_document_type="Progress Note",
        narrative_summary="Assessment and Plan: continue metformin as directed.",
        follow_up=[],
    )
    data.update(overrides)
    return DocumentSummary(**data)


class _StubResult:
    def __init__(self, output):
        self.output = output


class _StubAgent:
    """Stands in for AttachmentSummarizationChain.extraction_agent -- avoids constructing a
    real pydantic_ai Agent (which requires OPENAI_API_KEY via get_pydantic_ai_model())."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.call_count = 0

    async def run(self, prompt, **kwargs):
        self.call_count += 1
        index = min(self.call_count - 1, len(self._outputs) - 1)
        return _StubResult(self._outputs[index])


# --- 1-3: chunk sizing ---


def test_25k_document_produces_one_batch_not_three():
    """At the old CHUNK_CHAR_LIMIT=12,000, a ~25k document required 3 overlapping chunks;
    at BATCH_CHAR_LIMIT=30,000 it fits in 1."""
    batches = chain._create_batches([_doc("x" * 25_000)])
    assert len(batches) == 1


def test_every_character_of_a_70k_document_appears_in_some_chunk():
    text = "".join(chr(ord("a") + (i % 26)) for i in range(70_000))
    batches = chain._create_batches([_doc(text)])
    assert len(batches) > 1

    covered = bytearray(len(text))
    for batch in batches:
        chunk_doc = batch[0]
        offset = int(chunk_doc.resource_id.rsplit(":chunk:", 1)[1])
        chunk_len = len(chunk_doc.extracted_text)
        # The chunk's own text must actually be the corresponding slice of the source --
        # not just an offset claim.
        assert chunk_doc.extracted_text == text[offset:offset + chunk_len]
        for i in range(offset, offset + chunk_len):
            covered[i] = 1

    assert all(covered), "every character of the source document must land in some chunk"


def test_every_chunk_extracted_text_is_within_batch_char_limit():
    """Asserted on the individual chunk, not the assembled prompt -- _format_batch_prompt's
    per-document header can push the final prompt marginally over BATCH_CHAR_LIMIT, which is
    expected and out of scope here."""
    batches = chain._create_batches([_doc("y" * 70_000)])
    assert len(batches) > 1
    for batch in batches:
        assert len(batch[0].extracted_text) <= chain.BATCH_CHAR_LIMIT


# --- 4: _check_follow_up_grounding, unit-tested directly ---


def test_check_follow_up_grounding_drops_unsupported_keeps_supported():
    source = "Assessment and Plan: return in 6 weeks for follow-up labs. No other instructions given."
    supported = FollowUpDetail(
        follow_up="Return in 6 weeks",
        source_quote="return in 6 weeks for follow-up labs",
    )
    unsupported = FollowUpDetail(
        follow_up="See a specialist next year",
        source_quote="you must see a specialist in exactly one year for a full workup",
    )
    summary = _summary(follow_up=[supported, unsupported])

    _, dropped = chain._check_follow_up_grounding([summary], source)

    assert [detail.source_quote for detail in summary.follow_up] == [supported.source_quote]
    assert dropped == [unsupported.source_quote]


# --- 5: reachability from _extract_batch_attempt ---


@pytest.mark.asyncio
async def test_check_follow_up_grounding_is_reached_from_extract_batch_attempt(monkeypatch):
    text = "Assessment and Plan: return in 6 weeks for follow-up labs."
    doc = _doc(text, resource_id="doc-5")
    summary = _summary(
        source_document_id="doc-5",
        evidence_quotes=[text],
        follow_up=[
            FollowUpDetail(
                follow_up="Return in 6 weeks",
                source_quote="return in 6 weeks for follow-up labs",
            )
        ],
    )

    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary]])

    # scoped to chain.py's OWN _check_follow_up_grounding -- an unrelated helper of the same
    # name lives in test_procedure_extraction.py for a different module.
    spy = Mock(wraps=chain._check_follow_up_grounding)
    monkeypatch.setattr(chain, "_check_follow_up_grounding", spy)
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    token = chain._deferred_grounding.set([])
    try:
        result = await chain_instance._extract_batch_attempt([doc], 1, 1)
    finally:
        chain._deferred_grounding.reset(token)

    assert spy.called
    assert result[0].source_document_id == "doc-5"


# --- 6: the load-bearing test ---


@pytest.mark.asyncio
async def test_hallucinated_follow_up_still_fails_the_batch_closed(monkeypatch):
    text = "Assessment and Plan: continue metformin as directed."
    doc = _doc(text, resource_id="doc-6")
    hallucinated = FollowUpDetail(
        follow_up="Return in exactly three months for a repeat lab panel",
        source_quote="Return in exactly three months for a repeat lab panel",  # not in `text`
    )
    summary = _summary(
        source_document_id="doc-6",
        evidence_quotes=[text],
        follow_up=[hallucinated],
    )
    original_follow_up = list(summary.follow_up)

    chain_instance = chain.AttachmentSummarizationChain()
    # Same DocumentSummary object returned on both calls the stub agent is given.
    chain_instance._extraction_agent = _StubAgent([[summary], [summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._extract_batch([doc], 1, 1)

    # INVALID_SOURCE_EVIDENCE canonicalizes to CLINICAL_EVIDENCE_FAILED (document_extraction.py's
    # error-grouping table), which IS in _extract_batch's retry set -- one bounded repair
    # attempt, then the error escapes. Hence 2 stub calls, not 1.
    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"
    assert chain_instance._extraction_agent.call_count == 2

    # The mutation from _check_follow_up_grounding never reached the real object: paired with
    # test 5's reachability proof, this shows the wiring ran on deep copies only.
    assert summary.follow_up == original_follow_up
    assert summary.follow_up[0].source_quote == hallucinated.source_quote
