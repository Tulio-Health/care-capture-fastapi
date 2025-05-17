from enum import Enum

class LLM_MODEL(str, Enum):
    GPT_4O_MINI = "gpt-4o-mini"
    
class LLM_PROVIDER(str, Enum):
    OPENAI = "openai"