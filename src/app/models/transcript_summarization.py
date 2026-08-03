from uuid import UUID
from pydantic import BaseModel, Field

from src.app.models.attachment_summarization import DiagnosisDetail

class Transcript(BaseModel):
    text: str
    created_at: str
    language_code: str

class TranscriptSummarizationRequest(BaseModel):
    appointment_id: UUID
    transcripts:list[Transcript]
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
    recommendations_provided_by_provider: list[dict[str, str]] = Field(
        ...,
        description=(
            "Clinical recommendations, including lifestyle counseling (diet, exercise, activity) and "
            "in-progress medication adjustments discussed by the provider, each as {'recommendation': ...}."
        ),
    )
    procedures_mentioned: list[str] = Field(
        default_factory=list,
        description=(
            "Procedures or interventions performed during the visit (e.g., injections, aspirations, minor "
            "in-office procedures) discussed in the conversation."
        ),
    )
