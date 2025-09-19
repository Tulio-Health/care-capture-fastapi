from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List

from src.app.db.config.database import get_db
from src.app.services.translation.translation_service import TranslationService
from src.app.models.translation import TranslationRequest, TranslationResponse, PlaygroundTranslationRequest
from src.app.models.conversation_summaries import ConversationSummary
from src.app.chains.translation.chain import TranslationChain
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


@router.post(
    "/translate/playground",
    response_model=TranslationResponse,
    summary="Translation Playground",
    description="Translate conversation summaries without database dependencies. Auto-generates UUIDs and timestamps for simplified testing.",
    responses={
        200: {
            "description": "Successfully translated conversation summary",
            "content": {
                "application/json": {
                    "example": {
                        "summaryText": "El paciente presentó dolor en el pecho...",
                        "keyPoints": ["Dolor en el pecho", "Presión arterial elevada"],
                        "medications": [{"name": "Aspirina", "dosage": "81mg", "frequency": "diario"}],
                        "diagnoses": ["Hipertensión"],
                        "originalLanguage": "en",
                        "translatedLanguage": "es"
                    }
                }
            }
        },
        400: {"description": "Translation failed"},
        422: {"description": "Invalid request format"}
    }
)
async def translate_playground(
    request: PlaygroundTranslationRequest
) -> TranslationResponse:
    """
    Simplified translation playground for easy testing.
    
    Only requires medical content - all metadata (UUIDs, timestamps) is auto-generated.
    Uses the same core translation engine as production for identical quality.
    
    Benefits:
    - Zero logic duplication (reuses TranslationChain)
    - User-friendly: no complex IDs or timestamps required
    - Database-independent testing
    - Identical translation semantics to production
    """
    try:
        logger.info(f"Playground translation initiated for language: {request.language_code}")
        
        # Transform domain object to chain-compatible format
        summary_dict = _serialize_conversation_summary(request.conversation_summary)
        
        # Leverage existing translation abstraction
        translation_chain = TranslationChain()
        translated_data = await translation_chain.translate_conversation_summary(
            summary_dict, request.language_code
        )
        
        # Enrich with translation metadata
        translated_data.update({
            "original_language": "en",
            "translated_language": request.language_code
        })
        
        # Apply response transformation pipeline
        return _build_translation_response(translated_data)
        
    except Exception as e:
        logger.error(f"Playground translation failure: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Translation failed: {str(e)}")


def _serialize_conversation_summary(summary) -> Dict[str, Any]:
    """Convert domain object to translation chain input format."""
    return {
        "id": str(summary.id),
        "appointment_id": str(summary.appointment_id),
        "user_id": str(summary.user_id),
        "summary_text": summary.summary_text,
        "key_points": summary.key_points,
        "medications": summary.medications,
        "diagnoses": summary.diagnoses,
        "instructions": summary.instructions,
        "recommendations": summary.recommendations,
        "created_at": summary.created_at.isoformat(),
        "updated_at": summary.updated_at.isoformat(),
        "created_by": str(summary.created_by),
        "updated_by": str(summary.updated_by) if summary.updated_by else None
    }


def _build_translation_response(translated_data: Dict[str, Any]) -> TranslationResponse:
    """Transform translation output to API response format."""
    # Normalize temporal data for Pydantic
    for temporal_field in ["created_at", "updated_at"]:
        if isinstance(translated_data.get(temporal_field), str):
            translated_data[temporal_field] = datetime.fromisoformat(
                translated_data[temporal_field].replace("Z", "+00:00")
            )
    
    # Normalize identifier fields to proper types
    for uuid_field in ["id", "appointment_id", "user_id", "created_by", "updated_by"]:
        field_value = translated_data.get(uuid_field)
        if isinstance(field_value, str):
            translated_data[uuid_field] = UUID(field_value)
        elif field_value is None and uuid_field == "updated_by":
            # updated_by is Optional[UUID], so None is valid
            translated_data[uuid_field] = None
    
    return TranslationResponse(**translated_data)
