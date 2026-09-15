"""Guards the AI_SUMMARY_IMPROVEMENT_REVIEW.md fixes: official/lay diagnosis split,
procedures_mentioned, and the loosened recommendations guardrail. Not full coverage —
one small check per change so a regression fails loudly.
"""

from pathlib import Path
from typing import List

from src.app.chains.attachment_summarization.chain import _enforce_performed_cardinality
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DiagnosisDetail,
    DocumentSummary,
    RecommendationDetail,
)
from src.app.models.transcript_summarization import TranscriptSummarizationResponse


def test_diagnosis_detail_has_official_and_lay_fields():
    detail = DiagnosisDetail(
        official_diagnosis="Left shoulder pain following distal clavicle resection",
        lay_explanation="Ongoing shoulder pain after your collarbone surgery",
    )
    assert detail.official_diagnosis
    assert detail.lay_explanation


def test_document_summary_diagnoses_use_diagnosis_detail():
    assert DocumentSummary.model_fields["diagnoses"].annotation == List[DiagnosisDetail]


def test_attachment_summarization_response_has_procedures_and_split_diagnoses():
    fields = AttachmentSummarizationResponse.model_fields
    assert "procedures_mentioned" in fields
    assert fields["diagnoses_mentioned"].annotation == List[DiagnosisDetail]


def test_transcript_summarization_response_has_procedures_and_split_diagnoses():
    fields = TranscriptSummarizationResponse.model_fields
    assert "procedures_mentioned" in fields
    assert fields["medical_diagnoses_discussed"].annotation == list[DiagnosisDetail]


def test_transcript_recommendations_use_recommendation_detail() -> None:
    assert (
        TranscriptSummarizationResponse.model_fields[
            "recommendations_provided_by_provider"
        ].annotation
        == list[RecommendationDetail]
    )


def test_performed_sink_is_sourced_only_from_the_performed_bucket():
    """procedures_mentioned must never surface an item that only appears in the ordered/not_stated
    bucket. _enforce_performed_cardinality is the guard: if the synthesis agent over-produces
    relative to the performed bucket, output is truncated to the performed items themselves.
    """
    split = [
        {
            "procedures_performed": ["Left shoulder injection"],
            "procedures_ordered": ["Thyroid ultrasound"],
        }
    ]
    response = AttachmentSummarizationResponse(
        clinical_summary="x",
        documents_analyzed=1,
        procedures_mentioned=["Left shoulder injection", "Thyroid ultrasound"],
    )

    _enforce_performed_cardinality(response, split)

    assert response.procedures_mentioned == ["Left shoulder injection"]


def test_recommendations_guardrail_no_longer_bans_lifestyle_counseling():
    chain_source = (
        Path(__file__).parents[2]
        / "chains"
        / "attachment_summarization"
        / "chain.py"
    ).read_text()
    assert "no general educational" not in chain_source.lower()
    assert "no direct patient actions" not in chain_source.lower()


def test_extraction_prompt_pins_the_procedures_section():
    """PR-3a tightening (see §7 Check 5 in revision-round3.md): bounds the check to a prefix
    of the extraction prompt ending right before Section 8 (Follow-Up) so this assertion can't
    silently start passing because of unrelated content added later in the prompt.
    """
    chain_source = (
        Path(__file__).parents[2] / "chains" / "attachment_summarization" / "chain.py"
    ).read_text()
    pinned = chain_source[: chain_source.lower().index("section 8:")]

    assert "Section 7: Procedures" in pinned
    assert "is an ORDER" in pinned
    assert 'NEVER default to "performed"' in pinned
