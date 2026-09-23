"""PR-12b (validation-logic consolidation): tests for the evidence_quotes drop-and-log
redesign (item 3), the diagnosis-wording and synthesis performed-set fuzzy matching (items 4-5),
the retried final-grounding check that replaced the deleted classifier calls at the end of
_analyze (item 6), and confirmation that the ordered-vs-performed deterministic gate (item 8)
is unaffected by any of the above.

See test_clinical_grounding.py for the validate_high_risk_claims/validate_explicit_facts
deletion tests (items 1-2). Minimal local copies of test_attachment_chunking.py's
_doc/_summary/_StubAgent helpers are used here to keep this file self-contained and reviewable
as one unit for a safety-critical PR.
"""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DiagnosisDetail,
    DocumentAttachment,
    DocumentSummary,
    ProcedureMention,
)
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ingestion import mark_parsed


def _doc(text: str, resource_id: str = "doc-1") -> DocumentAttachment:
    return mark_parsed(DocumentAttachment(
        file_path=f"s3://bucket/{resource_id}.txt",
        content_type="text/plain",
        title="Progress Note",
        extracted_text=text,
        resource_id=resource_id,
    ))


def _summary(**overrides) -> DocumentSummary:
    data = dict(
        source_document_id="doc-1",
        evidence_quotes=["placeholder"],
        source_document_title="Progress Note",
        source_document_type="Progress Note",
        narrative_summary="placeholder",
    )
    data.update(overrides)
    return DocumentSummary(**data)


class _StubResult:
    def __init__(self, output):
        self.output = output


class _StubAgent:
    """Stands in for AttachmentSummarizationChain.extraction_agent."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.call_count = 0

    async def run(self, prompt, **kwargs):
        self.call_count += 1
        index = min(self.call_count - 1, len(self._outputs) - 1)
        return _StubResult(self._outputs[index])


# --- item 3: evidence_quotes drop-and-log ---

@pytest.mark.asyncio
async def test_multi_clause_paraphrased_evidence_quote_survives_via_drop_and_log(monkeypatch):
    """PR-12 research topic A: a single evidence_quote that rolls up several source rows
    used to fail the WHOLE batch closed via a verbatim `q not in source` check. It must now
    be dropped and logged, while the summary's OTHER, well-supported evidence survives --
    the batch is no longer destroyed.

    Audit R9 note: the original aggregating example differed from the source by ONE
    character (a ';' for a newline), which the fixed windowed true-similarity metric
    correctly accepts as near-verbatim. The rolled-up quote below is genuinely paraphrased
    and reordered, so it stays unsupported under both the old and the fixed metric."""
    source = (
        "Home Medications:\n"
        "aspirin 81 mg Cap 81 each, Oral, Daily\n"
        "atorvastatin (LIPITOR) 20 mg, Oral, Daily\n"
    )
    aggregating_quote = (
        "Current home medication list includes atorvastatin twenty milligrams by mouth "
        "each day as well as daily oral low-dose aspirin 81"
    )
    supported_quote = "aspirin 81 mg Cap 81 each, Oral, Daily"
    doc = _doc(source, resource_id="doc-evq")
    summary = _summary(
        source_document_id="doc-evq",
        evidence_quotes=[aggregating_quote, supported_quote],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    token = chain._deferred_grounding.set([])
    try:
        result = await chain_instance._extract_batch_attempt([doc], 1, 1)
    finally:
        chain._deferred_grounding.reset(token)

    assert result[0].evidence_quotes == [supported_quote]


@pytest.mark.asyncio
async def test_dropped_evidence_quote_is_actually_logged(monkeypatch, caplog):
    """The dropped, unsupported evidence quote must be logged (content-hashed), not silently
    discarded."""
    source = "aspirin 81 mg Cap 81 each, Oral, Daily\n"
    aggregating_quote = (
        "Home Medications: aspirin 81 mg Cap 81 each, Oral, Daily; "
        "atorvastatin 20 mg, Oral, Daily"
    )
    doc = _doc(source, resource_id="doc-evq-2")
    summary = _summary(
        source_document_id="doc-evq-2",
        evidence_quotes=[aggregating_quote, "aspirin 81 mg Cap 81 each, Oral, Daily"],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    token = chain._deferred_grounding.set([])
    try:
        with caplog.at_level("WARNING"):
            await chain_instance._extract_batch_attempt([doc], 1, 1)
    finally:
        chain._deferred_grounding.reset(token)

    assert any("dropped_ungrounded_evidence" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_evidence_quotes_still_fails_closed_when_zero_survive(monkeypatch):
    """An empty-evidence state is still a real problem worth failing closed on."""
    source = "Patient denies any symptoms today."
    doc = _doc(source, resource_id="doc-evq-3")
    summary = _summary(
        source_document_id="doc-evq-3",
        evidence_quotes=["The patient was started on an entirely fabricated medication regimen"],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary], [summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._extract_batch([doc], 1, 1)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"


@pytest.mark.asyncio
async def test_procedure_source_quote_with_zero_support_still_fails_closed(monkeypatch):
    """Negative control for item 3: procedure.source_quote (an atomic anchor field) stays a
    hard, fail-closed gate -- fuzzy matching loosens the comparison, not the fail-closed
    policy."""
    source = "Patient denies any procedures during this visit."
    doc = _doc(source, resource_id="doc-anchor")
    summary = _summary(
        source_document_id="doc-anchor",
        evidence_quotes=[source],
        procedures=[ProcedureMention(
            description="Fabricated appendectomy",
            status="performed",
            source_quote="Emergency appendectomy was performed successfully without complication",
        )],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary], [summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._extract_batch([doc], 1, 1)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"


# --- item 4: DIAGNOSIS_WORDING_NOT_GROUNDED fuzzy match ---

@pytest.mark.asyncio
async def test_diagnosis_wording_check_is_now_fuzzy_not_verbatim(monkeypatch):
    """PR-12b item 4: DIAGNOSIS_WORDING_NOT_GROUNDED now reuses _quote_supported instead of a
    verbatim substring check -- a diagnosis differing only by a trailing period the model added
    (not present at that position in source) must be accepted."""
    text = "Assessment: Type 2 diabetes mellitus\nPlan: continue metformin."
    doc = _doc(text, resource_id="doc-dx")
    summary = _summary(
        source_document_id="doc-dx",
        evidence_quotes=[text],
        diagnoses=[DiagnosisDetail(
            official_diagnosis="Type 2 diabetes mellitus.",
            lay_explanation="Type 2 diabetes",
        )],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    token = chain._deferred_grounding.set([])
    try:
        result = await chain_instance._extract_batch_attempt([doc], 1, 1)
    finally:
        chain._deferred_grounding.reset(token)

    assert result[0].diagnoses[0].official_diagnosis == "Type 2 diabetes mellitus."


@pytest.mark.asyncio
async def test_diagnosis_wording_check_still_fails_closed_on_zero_support(monkeypatch):
    text = "Assessment: Hypertension, well controlled."
    doc = _doc(text, resource_id="doc-dx-2")
    summary = _summary(
        source_document_id="doc-dx-2",
        evidence_quotes=[text],
        diagnoses=[DiagnosisDetail(
            official_diagnosis="Chronic kidney disease stage 3",
            lay_explanation="Kidney disease",
        )],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary], [summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._extract_batch([doc], 1, 1)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"


# --- item 5: synthesis performed-set fuzzy equality ---

@pytest.mark.asyncio
async def test_synthesis_paraphrased_performed_procedure_now_passes(monkeypatch):
    """PR-12b item 5: exact set equality between synthesis's procedures_mentioned and
    extraction's procedures_performed used to hard-fail on ANY paraphrase. A close paraphrase
    must now be accepted."""
    records = [{"procedures_performed": ["Left shoulder injection administered in clinic"]}]
    response = AttachmentSummarizationResponse(
        clinical_summary="x", documents_analyzed=1,
        procedures_mentioned=["Left shoulder injection administered in clinic today"],
    )
    run = AsyncMock(return_value=NS(output=response))
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()
    chain_instance._synthesis_agent = NS(run=run)
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    result = await chain_instance._synthesize_records_attempt({}, records, 1)

    assert result.procedures_mentioned == ["Left shoulder injection administered in clinic today"]


@pytest.mark.asyncio
async def test_synthesis_invented_performed_procedure_still_fails(monkeypatch):
    """Negative control: a procedure with NO correspondence at all in the performed bucket
    (not even loosely) must still raise -- this is the genuine invention this gate exists to
    catch."""
    records = [{"procedures_performed": ["Left shoulder injection"]}]
    response = AttachmentSummarizationResponse(
        clinical_summary="x", documents_analyzed=1,
        procedures_mentioned=["Left shoulder injection", "Emergency appendectomy"],
    )
    run = AsyncMock(return_value=NS(output=response))
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()
    chain_instance._synthesis_agent = NS(run=run)
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._synthesize_records_attempt({}, records, 1)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"


# --- item 6: retried final-grounding check for Regime B ---

@pytest.mark.asyncio
async def test_regime_b_final_grounding_retries_once_on_transient_judge_rejection(monkeypatch):
    """PR-12b item 6: chain.py's end-of-_analyze call used to be a bare, unretried
    validate_high_risk_claims/validate_explicit_facts call. It is now an actual verify_grounding
    (LLM judge) call, retried once -- verify_grounding is measured non-deterministic on
    identical input (PR-12 research topic C \u00a73.4), so a single spurious rejection must not kill
    the whole appointment."""
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()
    calls = AsyncMock(side_effect=[DocumentProcessingError("GROUNDING_VALIDATION_FAILED"), None])
    monkeypatch.setattr(chain, "verify_grounding", calls)
    response = AttachmentSummarizationResponse(clinical_summary="x", documents_analyzed=1)

    token = chain._deferred_grounding.set(None)  # Regime B
    try:
        await chain_instance._verify_final_with_retry("source text", response)
    finally:
        chain._deferred_grounding.reset(token)

    assert calls.await_count == 2


@pytest.mark.asyncio
async def test_regime_b_final_grounding_propagates_a_persistent_rejection(monkeypatch):
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()
    failure = DocumentProcessingError("GROUNDING_VALIDATION_FAILED")
    calls = AsyncMock(side_effect=[failure, failure])
    monkeypatch.setattr(chain, "verify_grounding", calls)
    response = AttachmentSummarizationResponse(clinical_summary="x", documents_analyzed=1)

    token = chain._deferred_grounding.set(None)
    try:
        with pytest.raises(DocumentProcessingError):
            await chain_instance._verify_final_with_retry("source text", response)
    finally:
        chain._deferred_grounding.reset(token)

    assert calls.await_count == 2


@pytest.mark.asyncio
async def test_regime_a_skips_the_new_check_verify_final_already_covers_it(monkeypatch):
    """For Regime A (_deferred_grounding is a list), _verify_final's own single audit already
    checks the final response against real source -- the new retried check must be a no-op
    here, not a duplicate LLM call."""
    chain_instance = chain.AttachmentSummarizationChain()
    calls = AsyncMock()
    monkeypatch.setattr(chain, "verify_grounding", calls)
    response = AttachmentSummarizationResponse(clinical_summary="x", documents_analyzed=1)

    token = chain._deferred_grounding.set([])
    try:
        await chain_instance._verify_final_with_retry("source text", response)
    finally:
        chain._deferred_grounding.reset(token)

    calls.assert_not_awaited()


@pytest.mark.asyncio
async def test_regime_b_final_grounding_skips_gracefully_when_over_budget(monkeypatch):
    """Empirically found running the real Ricardo Febry case: Regime B means source >
    80,000 chars by definition, so accepted_source routinely exceeds verify_grounding's own
    budget before the judge is ever called. This must be skipped gracefully, not treated as a
    rejection that kills the appointment."""
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._model = object()
    calls = AsyncMock()
    monkeypatch.setattr(chain, "verify_grounding", calls)
    oversized_source = "x" * (chain.GROUNDING_MAX_CHARACTERS + 1)
    response = AttachmentSummarizationResponse(clinical_summary="x", documents_analyzed=1)

    token = chain._deferred_grounding.set(None)  # Regime B
    try:
        await chain_instance._verify_final_with_retry(oversized_source, response)
    finally:
        chain._deferred_grounding.reset(token)

    calls.assert_not_awaited()


# --- item 8: confirm the ordered-vs-performed gate is unaffected (DO NOT TOUCH) ---

@pytest.mark.asyncio
async def test_ordered_vs_performed_gate_still_fails_closed_on_an_ordered_quote(monkeypatch):
    """PR-12b item 8: chain.py's ordered-vs-performed regex gate must be byte-identical and
    behaviorally unaffected by every other PR-12b change."""
    text = "Procedures  Ultrasound Neck Thyroid ordered for further evaluation."
    doc = _doc(text, resource_id="doc-gate")
    summary = _summary(
        source_document_id="doc-gate",
        evidence_quotes=[text],
        procedures=[ProcedureMention(
            description="Thyroid ultrasound",
            status="performed",
            source_quote=text,
        )],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary], [summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    with pytest.raises(DocumentProcessingError) as excinfo:
        await chain_instance._extract_batch([doc], 1, 1)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"


@pytest.mark.asyncio
async def test_ordered_vs_performed_gate_still_passes_a_genuinely_performed_quote(monkeypatch):
    text = "A shoulder injection was administered in clinic today."
    doc = _doc(text, resource_id="doc-gate-2")
    summary = _summary(
        source_document_id="doc-gate-2",
        evidence_quotes=[text],
        procedures=[ProcedureMention(
            description="Shoulder injection",
            status="performed",
            source_quote=text,
        )],
    )
    chain_instance = chain.AttachmentSummarizationChain()
    chain_instance._extraction_agent = _StubAgent([[summary]])
    monkeypatch.setattr(chain, "verify_grounding", AsyncMock())

    token = chain._deferred_grounding.set([])
    try:
        result = await chain_instance._extract_batch_attempt([doc], 1, 1)
    finally:
        chain._deferred_grounding.reset(token)

    assert result[0].procedures[0].status == "performed"
