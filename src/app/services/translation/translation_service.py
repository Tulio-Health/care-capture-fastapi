from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import json

from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from src.app.chains.translation.chain import TranslationChain
from src.app.common.logging import get_logger

logger = get_logger(__name__)

class TranslationService:
    """
    Service for translating conversation summaries to different languages.
    
    This service provides:
    - Translation of medical conversation summaries
    - Error handling and logging
    - Data validation and integrity checks
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ConversationSummariesRepository(db)
        self.translation_chain = TranslationChain()
    

    
    async def translate_conversation_summary(
        self, 
        summary_id: UUID, 
        language_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Translate a conversation summary to the specified language.
        
        Args:
            summary_id: ID of the conversation summary to translate
            language_code: Target language code (e.g., 'es', 'fr', 'de')
            
        Returns:
            Translated conversation summary as a dictionary
            
        Raises:
            ValueError: If summary not found or translation fails
        """
        try:
            # Get original summary from database
            summary = await self.repository.get_by_id(summary_id)
            if not summary:
                raise ValueError(f"Conversation summary with ID {summary_id} not found")
            
            logger.info(f"Retrieved summary {summary_id} for translation to {language_code}")
            
            # Convert to dict for translation
            summary_dict = {
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
                "updated_by": str(summary.updated_by)
            }
            
            # Translate the summary
            translated_summary = await self.translation_chain.translate_conversation_summary(
                summary_dict, language_code
            )
            
            # Add translation metadata
            translated_summary["original_language"] = "en"
            translated_summary["translated_language"] = language_code
            
            # Validate that all required fields are present
            required_fields = [
                "id", "appointment_id", "user_id", "summary_text", 
                "created_at", "updated_at", "created_by", "updated_by"
            ]
            
            for field in required_fields:
                if field not in translated_summary:
                    raise ValueError(f"Translation missing required field: {field}")
            
            # Create TranslationResponse object to ensure proper camelCase serialization
            from src.app.models.translation import TranslationResponse
            
            translation_response = TranslationResponse(
                id=translated_summary["id"],
                appointment_id=translated_summary["appointment_id"],
                user_id=translated_summary["user_id"],
                summary_text=translated_summary["summary_text"],
                key_points=translated_summary.get("key_points"),
                medications=translated_summary.get("medications"),
                diagnoses=translated_summary.get("diagnoses"),
                instructions=translated_summary.get("instructions"),
                recommendations=translated_summary.get("recommendations"),
                original_language=translated_summary["original_language"],
                translated_language=translated_summary["translated_language"],
                created_at=translated_summary["created_at"],
                updated_at=translated_summary["updated_at"],
                created_by=translated_summary["created_by"],
                updated_by=translated_summary["updated_by"]
            )
            
            
            logger.info(f"Successfully translated summary {summary_id} to {language_code}")
            return translation_response.model_dump(by_alias=True)
            
        except ValueError as e:
            logger.error(f"Translation failed for summary {summary_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during translation of summary {summary_id}: {str(e)}")
            raise ValueError(f"Translation failed: {str(e)}")
    

