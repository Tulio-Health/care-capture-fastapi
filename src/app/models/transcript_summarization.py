from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from src.app.models.attachment_summarization import (
    DiagnosisDetail,
    RecommendationDetail,
)

class Transcript(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    created_at: str
    language_code: str

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO timestamp") from exc
        return value

class TranscriptSummarizationRequest(BaseModel):
    appointment_id: UUID
    transcripts:list[Transcript] = Field(min_length=1, max_length=1000)
    user_id: UUID


class TranscriptSummarizationResponse(BaseModel):
    provider_patient_discussion_summary_text: str = Field(
        ...,
        description=(
            "Patient-facing overview only \u2014 2-3 sentences: reason for the visit, what was done, the diagnosis "
            "cited from medical_diagnoses_discussed's official_diagnosis, and the single most important next step. "
            "Do NOT restate individual exam findings or measurements \u2014 those belong only in "
            "provider_patient_discussion_key_points."
        ),
    )
    provider_patient_discussion_key_points: list[str] = Field(
        ...,
        description="The most important bullet points from the history, exam, and objective findings discussed during the visit.",
    )
    medications_prescribed_by_provider: list[dict[str, str]] = Field(
        ...,
        description="Drug-based medications discussed or prescribed, each as {'name': ..., 'dosage': ...}.",
    )
    medical_diagnoses_discussed: list[DiagnosisDetail] = Field(
        ...,
        description=(
            "Diagnoses discussed during the visit. Each entry has official_diagnosis (the clinician's own "
            "verbatim wording \u2014 do NOT translate or simplify this field) and lay_explanation (one "
            "plain-language sentence)."
        ),
    )
    instructions_provided_by_provider: list[str] = Field(
        ..., description="Direct instructions the provider gave the patient to follow."
    )
    recommendations_provided_by_provider: list[RecommendationDetail] = Field(
        ...,
        description=(
            "Clinical recommendations, including lifestyle counseling (diet, exercise, activity) and "
            "in-progress medication adjustments discussed by the provider."
        ),
    )
    procedures_mentioned: list[str] = Field(
        default_factory=list,
        description=(
            "Procedures or interventions performed during the visit (e.g., injections, aspirations, minor "
            "in-office procedures) discussed in the conversation. Do NOT include a procedure that was only "
            "ordered, recommended, referred, or scheduled for a future visit — only what was actually "
            "performed during this visit belongs here."
        ),
    )
