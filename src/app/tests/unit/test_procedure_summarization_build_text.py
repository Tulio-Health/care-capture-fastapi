"""Unit tests for `_build_summary_text` in `procedure_summarization.py`, which builds the
patient-facing narrative sentence used as a procedure row's `summary_text` - replacing the
old bare `procedure_type` title so these rows match the single-paragraph prose convention
every other `conversation_summaries` row (attachment_summary/transcript/fhir_analysis) uses.
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


def test_summary_text_includes_human_readable_date_and_details():
    text = _build_summary_text(_summary())

    assert text.startswith("You had a Cardiac catheterization with coronary angioplasty")
    assert "on June 29, 2026." in text
    assert "2026-06-29" not in text  # ISO form must not leak into the narrative
    assert text.endswith("A catheter was inserted through your wrist to check your arteries.")


def test_null_date_omits_date_clause_with_no_punctuation_artifacts():
    text = _build_summary_text(_summary(procedure_date=None))

    assert text.startswith("You had a Cardiac catheterization with coronary angioplasty. ")
    assert " on " not in text
    assert " on ." not in text
    assert " on None" not in text


def test_malformed_date_falls_back_to_omitting_date_clause():
    text = _build_summary_text(_summary(procedure_date="not-a-date"))

    assert text.startswith("You had a Cardiac catheterization with coronary angioplasty. ")
    assert " on " not in text


def test_outcome_is_never_included_in_summary_text():
    text = _build_summary_text(_summary(outcome="A very distinctive outcome sentence."))

    assert "A very distinctive outcome sentence." not in text
    assert "distinctive" not in text


def test_no_embedded_newlines():
    text = _build_summary_text(_summary())

    assert "\n" not in text


def test_no_trailing_space_or_none_when_details_are_falsy():
    # procedure_details is a required field per the Pydantic model, but the construction
    # must not degrade to a trailing space or literal "None" if it were ever empty.
    text = _build_summary_text(_summary(procedure_details=""))

    assert text == "You had a Cardiac catheterization with coronary angioplasty on June 29, 2026."
    assert not text.endswith(" ")
    assert "None" not in text
