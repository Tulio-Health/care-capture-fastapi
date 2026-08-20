"""Unit tests for `_build_summary_text` in `procedure_summarization.py`, which builds the
patient-facing narrative used as a procedure row's `summary_text` - just `procedure_details`,
which is already real second-person narrative prose on its own, matching the single-paragraph
prose convention every other `conversation_summaries` row (attachment_summary/transcript/
fhir_analysis) uses. `procedure_type` and `procedure_date` are surfaced separately (`data.
procedure_type`, `summary_metadata.procedure_date`) rather than folded into this sentence.
"""

from src.app.models.procedure_summarization import NOT_DOCUMENTED_FOLLOW_UP, ProcedureSummary
from src.app.services.summarization.procedure_summarization import _build_summary_text


def _summary(**overrides) -> ProcedureSummary:
    defaults = dict(
        source_document_title="Procedure Note",
        procedure_type="Cardiac catheterization with coronary angioplasty",
        procedure_date="2026-06-29",
        performed_by=["Dr. A"],
        reason="You had chest pain.",
        procedure_details="A catheter was inserted through your wrist to check your arteries.",
        outcome="The procedure went well with no complications.",
        follow_up=NOT_DOCUMENTED_FOLLOW_UP,
        follow_up_source_quote=None,
    )
    defaults.update(overrides)
    return ProcedureSummary(**defaults)


def test_summary_text_is_procedure_details():
    text = _build_summary_text(_summary())

    assert text == "A catheter was inserted through your wrist to check your arteries."


def test_summary_text_excludes_procedure_type_and_date():
    text = _build_summary_text(_summary())

    assert "Cardiac catheterization" not in text
    assert "2026-06-29" not in text
    assert "June 29, 2026" not in text


def test_outcome_is_never_included_in_summary_text():
    text = _build_summary_text(_summary(outcome="A very distinctive outcome sentence."))

    assert "A very distinctive outcome sentence." not in text
    assert "distinctive" not in text


def test_no_embedded_newlines():
    text = _build_summary_text(_summary())

    assert "\n" not in text


def test_empty_procedure_details_passes_through_as_is():
    # procedure_details is a required field per the Pydantic model, but the empty-string
    # edge case must not be silently rewritten (e.g. to "None" or padded with a fallback).
    text = _build_summary_text(_summary(procedure_details=""))

    assert text == ""
