"""
Factory for creating LLM models with SSM-loaded configuration
"""
from functools import lru_cache
from langchain.chat_models import init_chat_model
from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.settings import get_settings
import logging

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_chat_model(model_name: str = LLM_MODEL.GPT_4O_MINI, temperature: float = 0.2):
    """
    Get or create a chat model with SSM-loaded OpenAI API key.
    This function is cached to avoid recreating the model multiple times.
    
    Args:
        model_name: The model to use (default: GPT_4O_MINI)
        temperature: Model temperature (default: 0.2)
    
    Returns:
        Initialized chat model
    """
    settings = get_settings()
    
    if not settings.OPENAI_API_KEY:
        raise ValueError("OpenAI API key not configured. Check SSM parameters.")
    
    logger.info(f"Initializing chat model: {model_name} with temperature: {temperature}")
    
    model = init_chat_model(
        model=model_name,
        model_provider=LLM_PROVIDER.OPENAI,
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        # Without an explicit timeout, init_chat_model/ChatOpenAI ends up with
        # httpx Timeout(timeout=None) - a stalled connection hangs forever. Bound
        # it and cap retries so a stall fails within a predictable window instead.
        timeout=45,
        max_retries=1,
    )
    
    return model


def get_default_chat_model():
    """Get the default chat model with standard settings"""
    return get_chat_model(LLM_MODEL.GPT_4O_MINI, 0.2)


def get_creative_chat_model():
    """Get a chat model with higher temperature for creative tasks"""
    return get_chat_model(LLM_MODEL.GPT_4O_MINI, 0.7)


def get_pydantic_ai_model(model_name: str = LLM_MODEL.GPT_4O_MINI):
    """
    Create a PydanticAI OpenAI model with SSM-loaded API key.

    Args:
        model_name: The model to use (default: GPT_4O_MINI)

    Returns:
        Initialized OpenAIChatModel
    """
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise ValueError("OpenAI API key not configured. Check SSM parameters.")

    return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY))