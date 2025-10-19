from uuid import UUID
from pydantic import BaseModel, Field
from .transcript_summarization import TranscriptSummarizationResponse

class PlaygroundSummarizationRequest(BaseModel):
    """
    Request model for playground summarization endpoint.
    
    This model accepts plain text input for testing summarization
    without requiring appointment or user context.
    """
    plain_text: str = Field(..., description="Plain text conversation to summarize")
    request_id: UUID = Field(..., description="Unique identifier for this request")
    language_code: str = Field(default="en", description="Language code for the text")

class PlaygroundSummarizationResponse(BaseModel):
    """
    Response model for playground summarization endpoint.
    
    Returns the summarization results along with request metadata.
    Uses the same data structure as TranscriptSummarizationResponse for consistency.
    """
    request_id: UUID = Field(..., description="The request ID that was provided")
    data: TranscriptSummarizationResponse