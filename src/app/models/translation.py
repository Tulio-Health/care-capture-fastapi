from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from datetime import datetime
from src.app.common.constants.languages import LanguageCode
from src.app.models.conversation_summaries import ConversationSummary

class TranslationRequest(BaseModel):
    language_code: LanguageCode = Field(..., description="Target language code")

class PlaygroundConversationSummary(BaseModel):
    """Simplified conversation summary for playground testing with auto-generated metadata."""
    summary_text: str = Field(..., alias="summaryText", description="The main summary text of the conversation")
    key_points: Optional[List[str]] = Field(None, alias="keyPoints", description="Key points extracted from the conversation")
    medications: Optional[List[Dict[str, Any]]] = Field(None, alias="medications", description="Medications mentioned in the conversation")
    diagnoses: Optional[List[str]] = Field(None, alias="diagnoses", description="Diagnoses discussed in the conversation")
    instructions: Optional[List[str]] = Field(None, alias="instructions", description="Instructions provided during the conversation")
    recommendations: Optional[List[Dict[str, Any]]] = Field(None, alias="recommendations", description="Recommendations made during the conversation")
    
    # Auto-generated fields with sensible defaults
    id: UUID = Field(default_factory=uuid4, description="Auto-generated unique identifier")
    appointment_id: UUID = Field(default_factory=uuid4, description="Auto-generated appointment ID")
    user_id: UUID = Field(default_factory=uuid4, description="Auto-generated user ID")
    created_at: datetime = Field(default_factory=datetime.now, description="Auto-generated creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Auto-generated update timestamp")
    created_by: UUID = Field(default_factory=uuid4, description="Auto-generated creator ID")
    updated_by: Optional[UUID] = Field(default=None, description="Optional updater ID")
    
    class Config:
        """Pydantic model configuration."""
        populate_by_name = True  # Allow both camelCase and snake_case

class PlaygroundTranslationRequest(BaseModel):
    """Request model for translation playground endpoint."""
    conversation_summary: PlaygroundConversationSummary = Field(..., alias="conversationSummary", description="Simplified conversation summary for playground testing")
    language_code: LanguageCode = Field(..., alias="languageCode", description="Target language code for translation")
    
    class Config:
        """Pydantic model configuration."""
        populate_by_name = True  # Allow both camelCase and snake_case
    
class TranslationResponse(BaseModel):
    id: UUID = Field(alias="id")
    appointment_id: UUID = Field(alias="appointmentId")
    user_id: UUID = Field(alias="userId")
    summary_text: str = Field(alias="summaryText")
    key_points: Optional[List[str]] = Field(alias="keyPoints")
    medications: Optional[List[Dict[str, Any]]] = Field(alias="medications")
    diagnoses: Optional[List[str]] = Field(alias="diagnoses")
    instructions: Optional[List[str]] = Field(alias="instructions")
    recommendations: Optional[List[Dict[str, Any]]] = Field(alias="recommendations")
    original_language: str = Field(default="en", alias="originalLanguage")
    translated_language: str = Field(alias="translatedLanguage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    created_by: UUID = Field(alias="createdBy")
    updated_by: Optional[UUID] = Field(alias="updatedBy")

    class Config:
        """Pydantic model configuration."""
        from_attributes = True
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: str
        }
