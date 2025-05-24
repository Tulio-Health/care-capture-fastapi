from enum import Enum

class LLM_MODEL(str, Enum):
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    GPT_4_1 = "gpt-4-1"
    GPT_4_1_MINI = "gpt-4-1-mini"

class LLM_PROVIDER(str, Enum):
    OPENAI = "openai"