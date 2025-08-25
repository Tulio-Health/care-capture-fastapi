from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from src.app.common.constants.languages import LanguageCode

class TranslationRequest(BaseModel):
    language_code: LanguageCode = Field(..., description="Target language code")
    
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
    updated_by: UUID = Field(alias="updatedBy")

    class Config:
        """Pydantic model configuration."""
        from_attributes = True
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: str
        }
