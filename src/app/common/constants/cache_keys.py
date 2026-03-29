from enum import Enum

CACHE_KEY_PREFIX = "care-capture-cache-key"

# Node API's ioredis client auto-prepends CACHE_KEY_PREFIX to all keys
CHATBOT_USER_SUMMARIES_PREFIX = f"{CACHE_KEY_PREFIX}:chatbot:user-summaries"
CHATBOT_CONVERSATION_CONTEXT_PREFIX = f"{CACHE_KEY_PREFIX}:chatbot:conversation-context"

class CACHE_KEY(str, Enum):
    CONVERSATION_CHAT_HISTORY = "conversation"
    CONVERSATION_PROVIDER_VISIT_SUMMARY = "conversation:provider-visit-summary"
    CONVERSATION_PAST_APPOINTMENTS = "conversation:past-appointments"
    CONVERSATION_UPCOMING_APPOINTMENTS = "conversation:upcoming-appointments"
    CONVERSATION_USER_PROFILE = "conversation:user-profile"
    CONVERSATION_HEALTH_INSIGHTS = "conversation:health-insights"

    def format(self, identifier: str) -> str:
        return f"{CACHE_KEY_PREFIX}:{self.value}:{identifier}"


def chatbot_user_summaries_key(user_id: str) -> str:
    """Key for enriched summaries written by Node API."""
    return f"{CHATBOT_USER_SUMMARIES_PREFIX}:{user_id}"


def chatbot_conversation_context_key(conversation_id: str) -> str:
    """Key for follow-up conversation context written by FastAPI."""
    return f"{CHATBOT_CONVERSATION_CONTEXT_PREFIX}:{conversation_id}"
