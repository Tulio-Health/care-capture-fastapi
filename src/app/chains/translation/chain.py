from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from typing import Dict, Any
import json

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.common.logging import get_logger
from src.app.services.translation.medical_terminology import medical_terminology_service
from src.app.common.constants.languages import LanguageInfo

logger = get_logger(__name__)

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer

class TranslationChain:
    """
    A specialized translation chain for medical conversation summaries.
    
    This chain translates medical content while preserving:
    - Medical terminology accuracy
    - JSON structure integrity
    - Data types and field names
    - Critical medical information
    """
    
    def __init__(self):
        self._model = None
        self.parser = JsonOutputParser()
        
    @traceable(name="translate_conversation_summary")
    async def translate_conversation_summary(self, summary_data: Dict[str, Any], target_language: str) -> Dict[str, Any]:
        """
        Translate a conversation summary to the specified language.
        
        Args:
            summary_data: The conversation summary data to translate
            target_language: The target language code (e.g., 'es', 'fr', 'de')
            
        Returns:
            Translated conversation summary with the same structure
        """
        try:
            # Get semantic context and terminology for the target language
            semantic_context = medical_terminology_service.enhance_translation_prompt(target_language)
            
            # Create specialized prompt for medical content translation
            prompt = ChatPromptTemplate.from_messages([
                ("system", f"""You are a professional medical translator with expertise in healthcare terminology and semantic understanding. 
                Your task is to translate the provided medical conversation summary to {{target_language}} with semantic accuracy.
                
                CRITICAL TRANSLATION RULES:
                1. **Maintain Exact JSON Structure**: Keep all field names, data types, and structure identical
                2. **Semantic Translation**: Translate with semantic understanding, not just word-for-word
                3. **Medical Terminology**: Use culturally appropriate medical terminology for the target language
                4. **Medication Names**: Translate medication names to appropriate local terminology when possible
                5. **Data Integrity**: Preserve all dates, numbers, UUIDs, and technical identifiers exactly as they are
                6. **Field Names**: Do NOT translate field names (id, appointment_id, user_id, etc.) - only translate content
                7. **Cultural Sensitivity**: Consider cultural differences in medical communication and terminology
                8. **Consistency**: Maintain consistent terminology throughout the translation
                9. **Natural Language**: Ensure translations sound natural and idiomatic in the target language
                
                {semantic_context}
                
                TRANSLATION SCOPE:
                - Translate: summary_text, key_points, diagnoses, instructions with semantic understanding
                - MEDICATIONS: Translate medication names, dosage, and frequency to appropriate local terminology
                - Translate recommendation descriptions with cultural context
                - Do NOT translate: field names, UUIDs, dates, numbers, technical identifiers
                
                Return ONLY the translated JSON object with the exact same structure."""),
                ("user", "Translate this medical conversation summary to {target_language}:\n\n{summary_data}")
            ])
            
            # Create the translation chain
            chain = prompt | self.model | self.parser
            
            # Execute translation
            result = await chain.ainvoke({
                "target_language": target_language,
                "summary_data": json.dumps(summary_data, ensure_ascii=False, indent=2)
            }, config={"callbacks": [get_tracer()]})
            
            logger.info(f"Successfully translated summary to {target_language}")
            return result
            
        except Exception as e:
            logger.error(f"Translation failed for language {target_language}: {str(e)}")
            raise ValueError(f"Translation failed: {str(e)}")
    
    @property
    def model(self):
        """Lazy load the model on first access"""
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model
    
    def get_supported_languages(self) -> list[str]:
        """Get list of supported language codes."""
        return LanguageInfo.get_supported_languages()
