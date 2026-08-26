"""Guards the AI_SUMMARY_IMPROVEMENT_REVIEW.md fixes: official/lay diagnosis split,
procedures_mentioned, and the loosened recommendations guardrail. Not full coverage —
one small check per change so a regression fails loudly.
"""

from pathlib import Path
from typing import List

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


def test_recommendations_guardrail_no_longer_bans_lifestyle_counseling():
    chain_source = (
        Path(__file__).parents[2]
        / "chains"
        / "attachment_summarization"
        / "chain.py"
    ).read_text()
    assert "no general educational" not in chain_source.lower()
    assert "no direct patient actions" not in chain_source.lower()
