from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List, Union
from uuid import UUID, uuid4
from datetime import datetime

def _validate_language_code(v: str) -> str:
    if not (len(v) == 2 and v.isalpha() and v.islower()):
        raise ValueError(f"language_code must be a valid ISO 639-1 code (2 lowercase letters), got: {v!r}")
    return v


class TranslatedSummary(BaseModel):
    """PydanticAI output model — contains only the translatable fields of a conversation summary."""
    summary_text: str
    key_points: Optional[List[str]] = None
    medications: Optional[List[Dict[str, Any]]] = None
    diagnoses: Optional[List[Union[str, Dict[str, Any]]]] = None
    instructions: Optional[List[str]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    procedures: Optional[List[Dict[str, Any]]] = None


class TranslationRequest(BaseModel):
    language_code: str = Field(..., description="Target language code (ISO 639-1, e.g. 'es', 'ar', 'fr')")

    @field_validator("language_code")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        return _validate_language_code(v)

class PlaygroundConversationSummary(BaseModel):
    """Simplified conversation summary for playground testing with auto-generated metadata."""
    summary_text: str = Field(..., alias="summaryText", description="The main summary text of the conversation")
    key_points: Optional[List[str]] = Field(None, alias="keyPoints", description="Key points extracted from the conversation")
    medications: Optional[List[Dict[str, Any]]] = Field(None, alias="medications", description="Medications mentioned in the conversation")
    diagnoses: Optional[List[Union[str, Dict[str, Any]]]] = Field(None, alias="diagnoses", description="Diagnoses discussed in the conversation")
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
    language_code: str = Field(..., alias="languageCode", description="Target language code (ISO 639-1, e.g. 'es', 'ar', 'fr')")

    @field_validator("language_code")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        return _validate_language_code(v)

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
    diagnoses: Optional[List[Union[str, Dict[str, Any]]]] = Field(alias="diagnoses")
    instructions: Optional[List[str]] = Field(alias="instructions")
    recommendations: Optional[List[Dict[str, Any]]] = Field(alias="recommendations")
    procedures: Optional[List[Dict[str, Any]]] = Field(default=None, alias="procedures")
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
