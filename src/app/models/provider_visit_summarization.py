from uuid import UUID
from pydantic import BaseModel

class ProviderVisitSummarizationRequest(BaseModel):
    transcript_id: UUID
    user_id: UUID
    text: str

class ProviderVisitSummarizationResponse(BaseModel):
    summary_text: str
    key_points: dict[str, list[str]]
    medications: list[dict[str, str]]
    diagnoses: list[dict[str, str]]
    instructions: list[dict[str, str]]
    recommendations: list[dict[str, str]]