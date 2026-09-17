"""Guards Bug 1 (ordered/referred procedures rendered as performed): the ProcedureMention status
split at the map stage, the internal performed/ordered bucketing, the cardinality-invariant guard
on procedures_mentioned, and the new Section 7 prompt block. Not full coverage — one small check
per behavior so a regression fails loudly.

Simplification note: per user request, ordered/recommended procedures are NOT surfaced in a
dedicated response field (no `procedures_ordered` on AttachmentSummarizationResponse) — the
existing summary_text/key_insights narrative already describes them correctly. The "ordered"
bucket below is internal-only: it feeds the cardinality guard and the synthesis prompt's input
JSON, never a response field.
"""

from pathlib import Path
from typing import List, Literal

from src.app.chains.attachment_summarization.chain import (
    _enforce_performed_cardinality,
    _split_procedures,
)
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DocumentSummary,
    ProcedureMention,
)


def test_procedure_mention_status_is_a_required_literal():
    fields = ProcedureMention.model_fields
    assert fields["status"].is_required()
    assert fields["status"].annotation == Literal["performed", "ordered", "not_stated"]


def test_document_summary_procedures_use_procedure_mention():
    assert (
        DocumentSummary.model_fields["procedures"].annotation == List[ProcedureMention]
    )


def test_procedure_mention_source_quote_is_a_required_field():
    """Guard: `source_quote` grounds a ProcedureMention's identity AND status - if this ever
    silently becomes optional again, every procedure claim in the split (performed/ordered/
    not_stated) loses its quote-grounding without any test noticing."""
    fields = ProcedureMention.model_fields
    assert fields["source_quote"].is_required()


def test_split_procedures_buckets_performed_by_description_and_ordered_not_stated_by_quote():
    """`_split_procedures` (chain.py:472-478) reports `procedures_performed` by plain-language
    `description`, but `procedures_ordered`/`procedures_not_stated` by verbatim `source_quote` -
    ordered/not-stated items are never surfaced to the synthesis prompt as a bare claim string,
    only as their exact grounding text. The two are also kept in separate keys, not merged
    (chain.py:466: "Unknown status remains distinct from an order")."""
    summary = DocumentSummary(
        source_document_id="doc-referral-1",
        evidence_quotes=[
            "A shoulder injection was administered in clinic today.",
            "Thyroid ultrasound was ordered for further evaluation.",
        ],
        source_document_title="Referral Note",
        source_document_type="Consultation Note",
        narrative_summary="x",
        procedures=[
            ProcedureMention(
                description="Shoulder injection",
                status="performed",
                source_quote="A shoulder injection was administered in clinic today.",
            ),
            ProcedureMention(
                description="Thyroid ultrasound",
                status="ordered",
                source_quote="Thyroid ultrasound was ordered for further evaluation.",
            ),
            ProcedureMention(
                description="Unclear procedure",
                status="not_stated",
                source_quote="Procedure history is otherwise unremarkable.",
            ),
        ],
    )

    split = _split_procedures([summary])

    assert split[0]["procedures_performed"] == ["Shoulder injection"]
    assert split[0]["procedures_ordered"] == [
        "Thyroid ultrasound was ordered for further evaluation."
    ]
    assert split[0]["procedures_not_stated"] == [
        "Procedure history is otherwise unremarkable."
    ]
    assert "procedures" not in split[0]


def test_cardinality_guard_fires_only_when_response_exceeds_performed_bucket():
    split = [
        {
            "procedures_performed": ["Left shoulder injection"],
            "procedures_ordered": ["Thyroid ultrasound"],
        }
    ]

    # Safe: response matches the performed bucket exactly -> untouched.
    safe = AttachmentSummarizationResponse(
        clinical_summary="x",
        documents_analyzed=1,
        procedures_mentioned=["Left shoulder injection"],
    )
    _enforce_performed_cardinality(safe, split)
    assert safe.procedures_mentioned == ["Left shoulder injection"]

    # Unsafe: response invented an extra entry beyond the performed bucket -> truncated.
    unsafe = AttachmentSummarizationResponse(
        clinical_summary="x",
        documents_analyzed=1,
        procedures_mentioned=["Left shoulder injection", "Thyroid ultrasound"],
    )
    _enforce_performed_cardinality(unsafe, split)
    assert unsafe.procedures_mentioned == ["Left shoulder injection"]


def test_cardinality_guard_does_not_fire_when_model_merges_performed_items():
    """Merging two performed items into one sentence is safe (fewer claims, all true)."""
    split = [
        {
            "procedures_performed": ["Shoulder injection", "Knee injection"],
            "procedures_ordered": [],
        }
    ]
    response = AttachmentSummarizationResponse(
        clinical_summary="x",
        documents_analyzed=1,
        procedures_mentioned=[
            "You received shoulder and knee injections during this visit"
        ],
    )

    _enforce_performed_cardinality(response, split)

    assert response.procedures_mentioned == [
        "You received shoulder and knee injections during this visit"
    ]


def test_chain_has_section_7_procedures_prompt_with_cda_rule_and_status_guard():
    chain_source = (
        Path(__file__).parents[2] / "chains" / "attachment_summarization" / "chain.py"
    ).read_text()

    assert "Section 7: Procedures" in chain_source
    assert "is an ORDER" in chain_source
    assert 'NEVER default to "performed"' in chain_source
    assert (
        "never narrate an ordered, scheduled or referred procedure as something that "
        "happened at this visit" in chain_source
    )


def test_procedures_ordered_is_not_a_response_field_by_design():
    """User-requested simplification: ordered/recommended procedures are not surfaced in a
    dedicated response field. Only the internal split (synthesis input + cardinality guard)
    knows about "ordered" — it is never written to AttachmentSummarizationResponse or persisted.
    """
    assert "procedures_ordered" not in AttachmentSummarizationResponse.model_fields
