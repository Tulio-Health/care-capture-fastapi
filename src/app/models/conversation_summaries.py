from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field

class ConversationSummary(BaseModel):
    """
    Pydantic model for conversation summaries.
    
    This model represents the structure of conversation summaries retrieved from the database,
    with proper type hints and validation for all fields.
    """
    id: UUID = Field(..., description="Unique identifier for the summary")
    appointment_id: UUID = Field(..., alias="appointmentId", description="ID of the associated appointment")
    user_id: UUID = Field(..., alias="userId", description="ID of the user this summary belongs to")
    summary_text: str = Field(..., alias="summaryText", description="The main summary text of the conversation")
    key_points: Optional[List[str]] = Field(None, alias="keyPoints", description="Key points extracted from the conversation")
    medications: Optional[List[Dict[str, Any]]] = Field(None, description="Medications mentioned in the conversation")
    diagnoses: Optional[List[str]] = Field(None, description="Diagnoses discussed in the conversation")
    instructions: Optional[List[str]] = Field(None, description="Instructions provided during the conversation")
    recommendations: Optional[List[Dict[str, Any]]] = Field(None, description="Recommendations made during the conversation")
    created_at: datetime = Field(..., alias="createdAt", description="Timestamp when the summary was created")
    updated_at: datetime = Field(..., alias="updatedAt", description="Timestamp when the summary was last updated")
    created_by: UUID = Field(..., alias="createdBy", description="ID of the user who created the summary")
    updated_by: Optional[UUID] = Field(None, alias="updatedBy", description="ID of the user who last updated the summary")

    class Config:
        """Pydantic model configuration."""
        from_attributes = True  # Allows creation from ORM model
        populate_by_name = True  # Allow both camelCase and snake_case
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: str
        }

 