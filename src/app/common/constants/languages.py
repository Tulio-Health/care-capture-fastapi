"""
Centralized language constants for the application.
Follows DRY principles to avoid hardcoding language codes throughout the codebase.
"""

from enum import Enum
from typing import List


class LanguageCode(str, Enum):
    """Supported language codes for the application."""
    SPANISH = "es"
    PORTUGUESE = "pt"
    MANDARIN = "zh"
    BENGALI = "bn"
    HINDI = "hi"


class LanguageName(str, Enum):
    """Human-readable language names."""
    SPANISH = "Spanish"
    PORTUGUESE = "Portuguese"
    MANDARIN = "Mandarin"
    BENGALI = "Bengali"
    HINDI = "Hindi"

class LanguageInfo:
    """Language information and metadata."""
    
    @staticmethod
    def get_supported_languages() -> List[str]:
        """Get list of supported language codes."""
        return [lang.value for lang in LanguageCode]
    
    @staticmethod
    def get_language_name(language_code: str) -> str:
        """Get human-readable language name from language code."""
        code_to_name = {
            LanguageCode.SPANISH: LanguageName.SPANISH,
            LanguageCode.PORTUGUESE: LanguageName.PORTUGUESE,
            LanguageCode.MANDARIN: LanguageName.MANDARIN,
            LanguageCode.BENGALI: LanguageName.BENGALI,
        }
        return code_to_name.get(language_code, "Unknown")
    
    @staticmethod
    def is_supported(language_code: str) -> bool:
        """Check if a language code is supported."""
        return language_code in LanguageInfo.get_supported_languages()
    
    @staticmethod
    def get_semantic_context(language_code: str) -> dict:
        """Get semantic context information for a language."""
        context_maps = {
            LanguageCode.SPANISH: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["usted", "tú"],
                "medical_honorifics": ["doctor", "doctora"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "24-hour"
            },
            LanguageCode.PORTUGUESE: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["você", "tu"],
                "medical_honorifics": ["doutor", "doutora"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "24-hour"
            },
            LanguageCode.MANDARIN: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["您", "你"],
                "medical_honorifics": ["医生", "大夫"],
                "measurement_preferences": "metric",
                "date_format": "YYYY-MM-DD",
                "time_format": "24-hour"
            },
            LanguageCode.BENGALI: {
                "sentence_structure": "Subject-Object-Verb (SOV)",
                "formality_levels": ["আপনি", "তুমি", "তুই"],
                "medical_honorifics": ["ডাক্তার", "চিকিৎসক"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "12-hour with AM/PM"
            }
        }
        return context_maps.get(language_code, {})
