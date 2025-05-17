"""
This module implements the core intent identification chain using LangChain.

The module provides:
- IntendIdentifierChain: A class that uses LLM to identify the intent of user messages
- Model initialization with proper settings
- Intent classification logic
"""

from typing import Sequence
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER

from ...core import get_settings
from .models import RouterOptions
from .constants import INTENT_IDENTIFIER_SYSTEM_PROMPT

# Initialize model with settings
settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

class IntendIdentifierChain:
    """
    A chain that identifies the intent of user messages using LLM.
    
    This chain:
    1. Takes a sequence of messages as input
    2. Uses a specialized prompt to determine the intent
    3. Returns one of the predefined RouterOptions
    
    The chain is designed to be used in both API and CLI contexts.
    """
    
    def __init__(self):
        """
        Initializes the chain with a specialized prompt template.
        
        The prompt template is designed to:
        - Provide clear instructions to the LLM
        - Ensure consistent output format
        - Handle different types of queries appropriately
        """
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_IDENTIFIER_SYSTEM_PROMPT),
            ("human", """Conversation history:
            {messages}
            
            Based on this conversation, which assistant should handle the next message?""")
        ])
        
        self.chain = self.prompt | model | StrOutputParser()

    def identify_intent(self, messages: Sequence[HumanMessage]) -> str:
        """
        Identifies the intent of a sequence of messages.
        
        Args:
            messages: A sequence of HumanMessage objects representing the conversation
            
        Returns:
            str: The identified intent (one of RouterOptions values)
            
        The method:
        1. Processes the messages through the chain
        2. Cleans and validates the output
        3. Returns a valid intent or defaults to GENERAL
        """
        result = self.chain.invoke({"messages": messages})
        # Clean the result to ensure it's one of our expected values
        result = result.strip().lower()
        if result not in [option.value for option in RouterOptions]:
            return RouterOptions.GENERAL.value
        return result 