import logging
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.chains.ai_chat_intents.not_found_intent.constants import (
    NO_DATA_FOUND_SYSTEM_PROMPT,
    NO_DATA_FOUND_USER_PROMPT
)

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer
logger = logging.getLogger(__name__)


class NoDataFoundIntentChain:
    def __init__(self):
        self._model = None
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", NO_DATA_FOUND_SYSTEM_PROMPT),
            ("user", NO_DATA_FOUND_USER_PROMPT)
        ])
        self._chain = None
    
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

    async def handle_intent(self, **kwargs) -> IntentResponse[None]:
        try:
            text = kwargs['text']
            context = kwargs.get('context', {})
            intent = kwargs.get('intent', 'unknown')
            search_details = kwargs.get('search_details', '')
            
            # Extract user profile and conversation history from context
            user_profile = context.get('user_profile', {})
            user_name = user_profile.get('name', 'there')
            chat_history = context.get('conversation_messages', [])
            
            ai_content_string = await self.chain.ainvoke({
                "text": text,
                "user_name": user_name,
                "conversation_history": json.dumps(chat_history, default=str),
                "intent": intent,
                "search_details": search_details
            }, config={"callbacks": [get_tracer()]})
            
            return IntentResponse[None](
                intent=kwargs.get('intent', 'unknown'), 
                responses=[IntentAiResponse(
                    type="text", 
                    content=ai_content_string, 
                    data=None
                )]
            )
            
        except Exception as e:
            logger.error(f"Error processing no data found response: {str(e)}")
            # Fallback to simple message if LLM fails
            fallback_message = "I couldn't find the information you're looking for. You can try asking about your past visits, upcoming appointments, health insights, or general medical questions."
            return IntentResponse[None](
                intent=kwargs.get('intent', 'unknown'), 
                responses=[IntentAiResponse(
                    type="text", 
                    content=fallback_message, 
                    data=None
                )]
            )
