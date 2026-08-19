"""PydanticAI translation chain for medical conversation summaries."""

import json
import logging
from typing import Dict, Any

from langsmith import traceable
from pydantic_ai import Agent

from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.common.constants.languages import LanguageInfo
from src.app.models.translation import TranslatedSummary
from src.app.services.translation.medical_terminology import medical_terminology_service

logger = logging.getLogger(__name__)

_TRANSLATION_SYSTEM_PROMPT = """You are a professional medical translator with expertise in healthcare terminology and semantic understanding.
Your task is to translate provided medical conversation summary fields into the requested target language with semantic accuracy.

CRITICAL TRANSLATION RULES:
1. Maintain semantic accuracy — translate meaning, not just words
2. Use culturally appropriate medical terminology for the target language
3. Translate medication names to appropriate local terminology when available
4. Preserve all numbers, dates, and numeric values exactly as they are
5. Do NOT translate field names — only translate content values
6. Use formal, clinically appropriate language
7. Ensure translations sound natural and idiomatic in the target language
8. Maintain consistent terminology throughout

TRANSLATION SCOPE:
- Translate: summary_text, key_points, diagnoses, instructions, recommendation descriptions
- Translate medication names, dosage instructions, and frequency descriptions to local terminology
- For each entry in procedures: translate reason, procedure_details, outcome, and follow_up
- Do NOT translate: field names (name, dosage, frequency keys), UUIDs, numeric values, units
- In procedures entries, return procedure_date, performed_by, procedure_type, source_document_title, and follow_up_source_quote exactly as given
- Preserve the exact number and order of procedures entries and their keys

Return only the translatable fields as a structured output."""


class TranslationChain:
    """
    PydanticAI-based translation chain for medical conversation summaries.

    Translates the content fields of a summary while preserving metadata
    (IDs, timestamps, etc.) from the original.
    """

    def __init__(self, system_prompt: str | None = None):
        self._model = None
        self._agent = None
        self._system_prompt = system_prompt or _TRANSLATION_SYSTEM_PROMPT

    @property
    def model(self):
        if self._model is None:
            self._model = get_pydantic_ai_model()
        return self._model

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                output_type=TranslatedSummary,
                system_prompt=self._system_prompt,
            )
        return self._agent

    @traceable(name="translate_conversation_summary")
    async def translate_conversation_summary(
        self, summary_data: Dict[str, Any], target_language: str
    ) -> Dict[str, Any]:
        """
        Translate the content fields of a conversation summary to the target language.

        Args:
            summary_data: The full conversation summary dict (snake_case keys)
            target_language: ISO 639-1 language code (e.g. 'es', 'ar', 'fr')

        Returns:
            Dict with translated content fields merged back with original metadata
        """
        try:
            language_name = LanguageInfo.get_language_name(target_language)
            if language_name == "Unknown":
                language_name = target_language

            semantic_context = medical_terminology_service.enhance_translation_prompt(target_language)

            translatable = {
                "summary_text": summary_data.get("summary_text", ""),
                "key_points": summary_data.get("key_points"),
                "medications": summary_data.get("medications"),
                "diagnoses": summary_data.get("diagnoses"),
                "instructions": summary_data.get("instructions"),
                "recommendations": summary_data.get("recommendations"),
            }
            if summary_data.get("procedures"):
                translatable["procedures"] = summary_data["procedures"]

            user_prompt = (
                f"Translate the following medical summary fields to {language_name} ({target_language}).\n\n"
            )
            if semantic_context:
                user_prompt += f"{semantic_context}\n\n"
            user_prompt += (
                f"Medical Summary Fields:\n"
                f"{json.dumps(translatable, ensure_ascii=False, indent=2)}"
            )

            result = await self.agent.run(user_prompt)
            translated: TranslatedSummary = result.output

            # Merge translated fields back with original metadata
            merged = dict(summary_data)
            merged.update({
                "summary_text": translated.summary_text,
                "key_points": translated.key_points,
                "medications": translated.medications,
                "diagnoses": translated.diagnoses,
                "instructions": translated.instructions,
                "recommendations": translated.recommendations,
                "procedures": translated.procedures,
            })

            logger.info(f"Successfully translated summary to {target_language}")
            return merged

        except Exception as e:
            logger.error(f"Translation failed for language {target_language}: {str(e)}")
            raise ValueError(f"Translation failed: {str(e)}")
