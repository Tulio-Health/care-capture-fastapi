from enum import Enum

CACHE_KEY_PREFIX = "care-capture-cache-key"

class CACHE_KEY(str, Enum):
    CONVERSATION    = "conversation"
    USER            = "user"
    VISIT           = "visit"
    HEALTH_INSIGHTS = "health_insights"

    def format(self, identifier: str) -> str:
        return f"{CACHE_KEY_PREFIX}:{self.value}:{identifier}"
