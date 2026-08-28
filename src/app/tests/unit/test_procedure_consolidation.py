"""Unit tests for `ProcedureConsolidator` (Task 1: consolidate duplicate procedure
extractions). All tests are fully mocked/deterministic - no real LLM calls, no OPENAI_API_KEY
required.

Covers:
  (a) two genuinely-duplicate entries (same date, near-identical type) get merged into one,
      with unioned performed_by and longest-text-wins fields.
  (b) two genuinely-different procedures that the heuristic flags as candidates (same date,
      similar wording) but the LLM confirms are NOT the same event -> no merge.
  (c) a single procedure is a no-op with ZERO LLM calls made.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.app.chains.procedure_extraction.chain import ExtractedProcedure
from src.app.chains.procedure_extraction.consolidation import (
    ProcedureConsolidator,
    _ConsolidationResponse,
    _PairConfirmation,
)
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummary,
)


def _summary(**overrides) -> ProcedureSummary:
    defaults = dict(
        source_document_title="Procedure Note",
        procedure_type="Cardiac catheterization with coronary angioplasty",
        procedure_date="2026-06-29",
        performed_by=["Dr. A"],
        reason="You had chest pain.",
        procedure_details="A catheter was inserted.",
        outcome="The procedure was successful.",
        follow_up=NOT_DOCUMENTED_FOLLOW_UP,
        follow_up_source_quote=None,
    )
    defaults.update(overrides)
    return ProcedureSummary(**defaults)


def _mock_agent(confirmations: list[_PairConfirmation]) -> SimpleNamespace:
    agent = SimpleNamespace()
    agent.run = AsyncMock(
        return_value=SimpleNamespace(
            output=_ConsolidationResponse(confirmations=confirmations)
        )
    )
    return agent


async def test_duplicate_procedures_are_merged():
    a = _summary(
        source_document_title="Cardiac Cath Procedure Note",
        performed_by=["Dr. Ahmed Ullah, MD"],
        reason="Short reason.",
        procedure_details="Short details.",
        outcome="Short outcome.",
        follow_up=NOT_DOCUMENTED_FOLLOW_UP,
        follow_up_source_quote=None,
    )
    b = _summary(
        source_document_title="Cardiac Catheterization Consult Note",
        performed_by=["Dr. Jane Smith, MD"],
        reason="This is a much longer reason with more clinical detail than the other one.",
        procedure_details="This is a much longer procedure_details field with more detail.",
        outcome="This is a much longer outcome field with more detail than the other one.",
        follow_up="You were told to follow up with cardiology in 2 weeks.",
        follow_up_source_quote="f/u with cardiology in 2 weeks",
    )
    extracted = [
        ExtractedProcedure(document_id="doc-1", summary=a),
        ExtractedProcedure(document_id="doc-2", summary=b),
    ]

    consolidator = ProcedureConsolidator()
    consolidator._agent = _mock_agent(
        [_PairConfirmation(pair_index=0, same_procedure=True)]
    )

    result = await consolidator.consolidate(extracted)

    assert len(result) == 1
    merged = result[0]
    assert sorted(merged.document_ids) == ["doc-1", "doc-2"]
    assert merged.source_count == 2
    assert set(merged.summary.performed_by) == {
        "Dr. Ahmed Ullah, MD",
        "Dr. Jane Smith, MD",
    }
    # Longest-text-wins per field.
    assert merged.summary.reason == b.reason
    assert merged.summary.procedure_details == b.procedure_details
    assert merged.summary.outcome == b.outcome
    # Real follow_up wins over the sentinel, with ITS OWN matching quote.
    assert merged.summary.follow_up == b.follow_up
    assert merged.summary.follow_up_source_quote == b.follow_up_source_quote
    consolidator._agent.run.assert_awaited_once()


async def test_distinct_procedures_flagged_by_heuristic_are_not_merged():
    """Same date + similar wording is enough for the heuristic to flag a candidate pair, but
    if the LLM confirms they are NOT the same event, consolidate() must leave them separate.
    """
    a = _summary(
        procedure_type="Cardiac catheterization with coronary angioplasty",
        procedure_date="2026-06-29",
        performed_by=["Dr. Ahmed Ullah, MD"],
        reason="Follow-up catheterization for recurrent chest pain.",
    )
    b = _summary(
        procedure_type="Cardiac catheterization with coronary angioplasty and stent",
        procedure_date="2026-06-29",
        performed_by=["Dr. Maria Chen, MD"],
        reason="Elective catheterization scheduled for a different indication entirely.",
    )
    extracted = [
        ExtractedProcedure(document_id="doc-1", summary=a),
        ExtractedProcedure(document_id="doc-2", summary=b),
    ]

    consolidator = ProcedureConsolidator()
    consolidator._agent = _mock_agent(
        [_PairConfirmation(pair_index=0, same_procedure=False)]
    )

    result = await consolidator.consolidate(extracted)

    assert len(result) == 2
    document_ids = sorted(item.document_ids[0] for item in result)
    assert document_ids == ["doc-1", "doc-2"]
    for item in result:
        assert item.source_count == 1
    consolidator._agent.run.assert_awaited_once()


async def test_single_procedure_is_a_noop_with_zero_llm_calls():
    extracted = [ExtractedProcedure(document_id="doc-1", summary=_summary())]

    with patch(
        "src.app.chains.procedure_extraction.consolidation.get_pydantic_ai_model"
    ) as mock_get_model:
        consolidator = ProcedureConsolidator()
        result = await consolidator.consolidate(extracted)

        mock_get_model.assert_not_called()

    assert len(result) == 1
    assert result[0].document_ids == ["doc-1"]
    assert result[0].summary == extracted[0].summary
