from uuid import UUID
from pydantic import BaseModel, Field

class PlaygroundSummarizationRequest(BaseModel):
    """
    Request model for playground summarization endpoint.
    
    This model accepts plain text input for testing summarization
    without requiring appointment or user context.
    """
    plain_text: str = Field(..., description="Plain text conversation to summarize")
    request_id: UUID = Field(..., description="Unique identifier for this request")
    language_code: str = Field(default="en", description="Language code for the text")

class PlaygroundSummarizationData(BaseModel):
    """
    Data model containing the summarization results.
    """
    provider_patient_discussion_summary_text: str
    provider_patient_discussion_key_points: list[str]
    medications_prescribed_by_provider: list[dict[str, str]]
    medical_diagnoses_discussed: list[str]
    instructions_provided_by_provider: list[str]
    recommendations_provided_by_provider: list[dict[str, str]]

class PlaygroundSummarizationResponse(BaseModel):
    """
    Response model for playground summarization endpoint.
    
    Returns the summarization results along with request metadata.
    """
    request_id: UUID = Field(..., description="The request ID that was provided")
    data: PlaygroundSummarizationData