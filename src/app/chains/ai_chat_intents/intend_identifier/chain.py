"""
This module implements the core intent identification chain using LangChain.

The module provides:
- IntendIdentifierChain: A class that uses LLM to identify the intent of user messages
- Model initialization with proper settings
- Intent classification logic with advanced conversation context handling
"""

from typing import Sequence
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
import logging
from datetime import datetime

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.common.logging import get_logger
from .models import RouterOptions
from .constants import INTENT_IDENTIFIER_SYSTEM_PROMPT

logger = get_logger(__name__)
_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer

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
        self._model = None
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_IDENTIFIER_SYSTEM_PROMPT),
            ("human", "Conversation history:\n{messages}\nLast user message:\n{text}\n\nRespond ONLY with the correct intent label.")
        ])
        
        self._chain = None

    def identify_intent(self, conversation_messages: Sequence, text: str) -> str:
        """
        Identifies the intent of a sequence of messages using advanced conversation analysis.
        
        Args:
            conversation_messages: A sequence of message objects (can be strings, dicts, or HumanMessage objects)
            text: The current user message text
            
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
            formatted_messages = self._format_conversation_history(conversation_messages)
            
            # Get today's date for context
            today_date = datetime.now().strftime("%Y-%m-%d (%A)")
            
            # Create prompt with today's date
            formatted_system_prompt = INTENT_IDENTIFIER_SYSTEM_PROMPT.format(today_date=today_date)
            prompt_with_date = ChatPromptTemplate.from_messages([
                ("system", formatted_system_prompt),
                ("human", "Conversation history:\n{messages}\nLast user message:\n{text}\n\nRespond ONLY with the correct intent label.")
            ])
            chain_with_date = prompt_with_date | self.model | StrOutputParser()
            
            # Process through the chain
            result = chain_with_date.invoke({
                "messages": formatted_messages, 
                "text": text
            })
            
            # Log the raw intent string before processing for debugging
            logger.info(f"Raw intent result from model: '{result}'")
            print(f"DEBUG: Raw intent result: '{result}'")
            
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

    def _format_conversation_history(self, messages: Sequence) -> str:
        """
        Formats conversation history for optimal context analysis with concise bullet list.
        
        Args:
            messages: Sequence of message objects (can be strings, dicts, or HumanMessage objects)
            
        Returns:
            str: Formatted conversation history with clear structure
        """
        if not messages:
            return "No conversation history available."
        
        formatted_lines = []
        
        # Format each message as a concise bullet point
        for i, message in enumerate(messages, 1):
            # Handle different message types
            content = self._extract_content_from_message(message)
            
            if content:
                # Determine if this is likely a user message or AI response
                if self._is_likely_ai_response(content):
                    formatted_lines.append(f"• AI: {content}")
                else:
                    formatted_lines.append(f"• User: {content}")
        
        return "\n".join(formatted_lines) if formatted_lines else "No conversation history available."

    def _extract_content_from_message(self, message) -> str:
        """
        Extracts content from different types of message objects.
        
        Args:
            message: Can be a string, dict, or HumanMessage object
            
        Returns:
            str: The extracted content or empty string if extraction fails
        """
        try:
            # If it's a HumanMessage object
            if hasattr(message, 'content'):
                return message.content.strip()
            
            # If it's a dictionary (parsed JSON from Redis)
            elif isinstance(message, dict):
                # Try different possible keys for content
                if 'content' in message:
                    return str(message['content']).strip()
                elif 'message' in message:
                    return str(message['message']).strip()
                elif 'text' in message:
                    return str(message['text']).strip()
                else:
                    # If it's a dict but no recognizable content key, convert to string
                    return str(message).strip()
            
            # If it's a plain string
            elif isinstance(message, str):
                return message.strip()
            
            # For any other type, convert to string
            else:
                return str(message).strip()
                
        except Exception as e:
            logger.warning(f"Failed to extract content from message: {e}")
            return ""

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
        
    @property
    def model(self):
        """Lazy load the model on first access"""
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model
    
    @property
    def chain(self):
        """Lazy load the chain on first access"""
        if self._chain is None:
            self._chain = self.prompt | self.model | StrOutputParser()
        return self._chain

        content_lower = content.lower()
        return any(indicator in content_lower for indicator in ai_indicators) or len(content) > 200 
