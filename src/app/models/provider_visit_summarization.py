from uuid import UUID
from pydantic import BaseModel

class Transcript(BaseModel):
    text: str
    created_at: str
    language_code: str

class ProviderVisitSummarizationRequest(BaseModel):
    appointment_id: UUID
    transcripts:list[Transcript]
    user_id: UUID


class ProviderVisitSummarizationResponse(BaseModel):
    provider_patient_discussion_summary_text: str
    provider_patient_discussion_key_points:list[str]
    medications_prescribed_by_provider: list[dict[str, str]]
    medical_diagnoses_discussed: list[str]
    instructions_provided_by_provider: list[str]
    recommendations_provided_by_provider: list[dict[str, str]]
