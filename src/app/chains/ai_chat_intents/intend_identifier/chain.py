"""
This module implements the core intent identification chain using LangChain.

The module provides:
- IntendIdentifierChain: A class that uses LLM to identify the intent of user messages
- Model initialization with proper settings
- Intent classification logic with advanced conversation context handling
"""

from typing import Sequence
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
import logging

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.core.settings import get_settings
from src.app.common.logging import get_logger
from .models import RouterOptions
from .constants import INTENT_IDENTIFIER_SYSTEM_PROMPT

# Initialize model with settings
settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.1,  # Lower temperature for more consistent classification
)

logger = get_logger(__name__)

tracer = LangSmithTrace().trace(tags=[__name__])

class IntendIdentifierChain:
    """
    An advanced intent identification chain that analyzes conversation context to accurately classify user intents.
    
    This chain:
    1. Takes a sequence of messages as input with full conversation context
    2. Uses sophisticated prompt engineering to determine intent
    3. Handles contextual references and follow-up questions
    4. Returns one of the predefined RouterOptions with high confidence
    
    The chain is designed to understand conversation flow and maintain context across multiple exchanges.
    """
    
    def __init__(self):
        """
        Initializes the chain with an advanced prompt template that emphasizes conversation context.
        
        The prompt template includes:
        - Role-based prompting for medical conversation analysis
        - Emotion prompting for patient safety emphasis
        - Few-shot examples for contextual classification
        - Clear decision framework for edge cases
        """
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_IDENTIFIER_SYSTEM_PROMPT),
            ("human", """Conversation history:
            {messages}
            
            Based on this conversation, which assistant should handle the next message? If the last message is not clear, look at the conversation history to determine what the intent can be.""")
        ])
        
        self.chain = self.prompt | model | StrOutputParser()

    def identify_intent(self, messages: Sequence[HumanMessage]) -> str:
        """
        Identifies the intent of a sequence of messages using advanced conversation analysis.
        
        Args:
            messages: A sequence of HumanMessage objects representing the conversation
            
        Returns:
            str: The identified intent (one of RouterOptions values)
            
        The method:
        1. Formats the conversation history for optimal context analysis
        2. Processes messages through the enhanced chain
        3. Validates and cleans the output
        4. Implements fallback logic for edge cases
        """
        try:
            # Format conversation history for better context understanding
            formatted_messages = self._format_conversation_history(messages)
            
            # Process through the chain
            result = self.chain.invoke({"messages": formatted_messages})
            
            # Clean and validate the result
            result = result.strip().lower().replace('"', '').replace("'", "")
            
            # Validate against known options
            valid_options = [option.value for option in RouterOptions]
            if result in valid_options:
                logger.info(f"Intent identified: {result}")
                return result
            
            # Log unexpected results for monitoring
            logger.warning(f"Unexpected intent result: '{result}', defaulting to not_a_valid_option")
            return RouterOptions.NOT_A_VALID_OPTION.value
            
        except Exception as e:
            logger.error(f"Error in intent identification: {str(e)}")
            return RouterOptions.NOT_A_VALID_OPTION.value

    def _format_conversation_history(self, messages: Sequence[HumanMessage]) -> str:
        """
        Formats conversation history for optimal context analysis.
        
        Args:
            messages: Sequence of HumanMessage objects
            
        Returns:
            str: Formatted conversation history with clear structure
        """
        if not messages:
            return "No conversation history available."
        
        formatted_lines = []
        
        # Add conversation context header
        formatted_lines.append("=== CONVERSATION CONTEXT ===")
        
        # Format each message with clear attribution and numbering
        for i, message in enumerate(messages, 1):
            content = message.content.strip()
            if content:
                # Determine if this is likely a user message or AI response
                if self._is_likely_ai_response(content):
                    formatted_lines.append(f"[{i}] AI Assistant: {content}")
                else:
                    formatted_lines.append(f"[{i}] User: {content}")
        
        # Add analysis focus
        formatted_lines.append("\n=== FOCUS ON LATEST MESSAGE ===")
        if messages:
            latest_message = messages[-1].content.strip()
            formatted_lines.append(f"Latest User Message: \"{latest_message}\"")
        
        return "\n".join(formatted_lines)

    def _is_likely_ai_response(self, content: str) -> bool:
        """
        Heuristic to determine if a message is likely an AI response.
        
        Args:
            content: Message content to analyze
            
        Returns:
            bool: True if likely an AI response, False if likely user message
        """
        ai_indicators = [
            "based on your", "i can help", "here's what", "according to",
            "i found", "let me", "i'll help", "here are", "i see that",
            "your appointments", "your visits", "your health", "i apologize"
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in ai_indicators) or len(content) > 200 
