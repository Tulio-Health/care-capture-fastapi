from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

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
    metadata: Optional[Dict[str, Any]] = Field(None, alias="summaryMetadata", description="Additional metadata about the summary (e.g., source, analysis version)")
    created_at: datetime = Field(..., alias="createdAt", description="Timestamp when the summary was created")
    updated_at: datetime = Field(..., alias="updatedAt", description="Timestamp when the summary was last updated")
    created_by: UUID = Field(..., alias="createdBy", description="ID of the user who created the summary")
    updated_by: Optional[UUID] = Field(None, alias="updatedBy", description="ID of the user who last updated the summary")

    @model_validator(mode='before')
    @classmethod
    def handle_sqlalchemy_metadata(cls, data: Any) -> Any:
        """
        Handle metadata field from SQLAlchemy entity.
        
        SQLAlchemy stores the metadata field as 'summary_metadata' in the entity
        but it gets mapped to 'metadata' in the database column.
        """
        if hasattr(data, '__dict__'):
            # Convert SQLAlchemy object to dict
            data = data.__dict__.copy()
        
        # Handle the metadata field mapping
        if isinstance(data, dict):
            # If summary_metadata exists, use it for metadata
            if 'summary_metadata' in data and 'metadata' not in data:
                data['metadata'] = data['summary_metadata']
            # Ensure metadata is a dict, not an object
            if 'metadata' in data and data['metadata'] is not None:
                if not isinstance(data['metadata'], dict):
                    # Try to convert to dict if possible
                    try:
                        data['metadata'] = dict(data['metadata'])
                    except (TypeError, ValueError):
                        data['metadata'] = None
        
        return data

    class Config:
        """Pydantic model configuration."""
        from_attributes = True  # Allows creation from ORM model
        populate_by_name = True  # Allow both camelCase and snake_case
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: str
        }

 