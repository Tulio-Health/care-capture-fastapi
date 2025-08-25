from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List

from src.app.db.config.database import get_db
from src.app.services.translation.translation_service import TranslationService
from src.app.models.translation import TranslationRequest, TranslationResponse
from src.app.common.constants.languages import LanguageCode
from src.app.common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/care-capture/conversation-summaries",
    tags=["translation"]
)

@router.post(
    "/{summary_id}/translate",
    response_model=TranslationResponse,
    summary="Translate Conversation Summary",
    description="Translate a conversation summary to the specified language",
    responses={
        200: {
            "description": "Successfully translated summary",
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "appointmentId": "123e4567-e89b-12d3-a456-426614174001",
                        "userId": "123e4567-e89b-12d3-a456-426614174002",
                        "summaryText": "El paciente presentó síntomas de dolor en el pecho...",
                        "keyPoints": ["Dolor en el pecho", "Presión arterial elevada"],
                        "medications": [{"name": "Aspirin", "dosage": "81mg", "frequency": "daily"}],
                        "diagnoses": ["Hipertensión", "Angina de pecho"],
                        "instructions": ["Tomar medicamentos según lo prescrito"],
                        "recommendations": [{"type": "Seguimiento", "description": "Visita de seguimiento en 2 semanas"}],
                        "originalLanguage": "en",
                        "translatedLanguage": "es",
                        "createdAt": "2024-01-15T10:30:00Z",
                        "updatedAt": "2024-01-15T10:30:00Z",
                        "createdBy": "123e4567-e89b-12d3-a456-426614174003",
                        "updatedBy": "123e4567-e89b-12d3-a456-426614174003"
                    }
                }
            }
        },
        404: {
            "description": "Conversation summary not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Conversation summary with ID 123e4567-e89b-12d3-a456-426614174000 not found"}
                }
            }
        },
        400: {
            "description": "Invalid language code or translation failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Translation failed: Invalid language code"}
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {"detail": [{"loc": ["body", "language_code"], "msg": "field required", "type": "value_error.missing"}]}
                }
            }
        }
    }
)
async def translate_conversation_summary(
    summary_id: UUID,
    request: TranslationRequest,
    db: AsyncSession = Depends(get_db)
) -> TranslationResponse:
    """
    Translate a conversation summary to the specified language.
    
    This endpoint translates medical conversation summaries while preserving:
    - Medical terminology accuracy
    - JSON structure integrity
    - Data types and field names
    - Critical medical information
    
    Args:
        summary_id: ID of the conversation summary to translate
        request: Translation request containing target language
        db: Database session
        
    Returns:
        Translated conversation summary
        
    Raises:
        HTTPException: If summary not found or translation fails
    """
    try:
        logger.info(f"Translation request received for summary {summary_id} to language {request.language_code}")
        
        translation_service = TranslationService(db)
        translated_summary = await translation_service.translate_conversation_summary(
            summary_id, request.language_code
        )
        
        # Convert string dates back to datetime for Pydantic validation
        if isinstance(translated_summary.get("created_at"), str):
            from datetime import datetime
            translated_summary["created_at"] = datetime.fromisoformat(translated_summary["created_at"].replace("Z", "+00:00"))
        if isinstance(translated_summary.get("updated_at"), str):
            from datetime import datetime
            translated_summary["updated_at"] = datetime.fromisoformat(translated_summary["updated_at"].replace("Z", "+00:00"))
        
        # Convert string UUIDs back to UUID objects
        for field in ["id", "appointment_id", "user_id", "created_by", "updated_by"]:
            if isinstance(translated_summary.get(field), str):
                translated_summary[field] = UUID(translated_summary[field])
        
        logger.info(f"Successfully translated summary {summary_id} to {request.language_code}")
        return TranslationResponse(**translated_summary)
        
    except ValueError as e:
        logger.error(f"Translation failed for summary {summary_id}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during translation of summary {summary_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Translation failed: {str(e)}")
