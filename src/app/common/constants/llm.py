from enum import Enum

class LLM_MODELS(str, Enum):
    GPT_4O_MINI = "gpt-4o-mini"
    
class LLM_PROVIDERS(str, Enum):
    OPENAI = "openai"