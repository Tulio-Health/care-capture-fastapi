from enum import Enum

CACHE_KEY_PREFIX = "care-capture-cache-key"

class CACHE_KEY(str, Enum):
    CONVERSATION_CHAT_HISTORY = "conversation"
    CONVERSATION_PROVIDER_VISIT_SUMMARY = "conversation:provider-visit-summary"
    CONVERSATION_PAST_APPOINTMENTS = "conversation:past-appointments"
    CONVERSATION_UPCOMING_APPOINTMENTS = "conversation:upcoming-appointments"

    def format(self, identifier: str) -> str:
        return f"{CACHE_KEY_PREFIX}:{self.value}:{identifier}"
