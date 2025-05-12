from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage

from src.app.chains.chat import MedicalChatChain
from src.app.chains.intent_router import IntentRouter
from src.app.chains.intend_identifier import IntendIdentifierChain
from src.app.models.provider_visit_summarization import ProviderVisitSummarizationResponse
from src.app.routes.intend_identify import IntentResponse

from ..db.config.database import get_db
from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from src.app.models.chat import ChatRequest
from src.app.cache.redis import redis_client

router = APIRouter(
    prefix="/care-capture/ai-chat",
    tags=["care-capture-chat"]
)

redis = redis_client.client

@router.post('/',
             response_model=IntentResponse,
             status_code=200)
async def chat(chat_request: ChatRequest, db: AsyncSession = Depends(get_db)):
    print(f"Chat request: {chat_request}")
    try:
        conversation_id = chat_request.conversation_id
        chat_ctx = redis.lrange(f"care-capture-cache-key:conversation:{conversation_id}", 0, -1)
        
        if not chat_ctx:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        context = dict()
        context["user_profile"] = "Patient Profile"
        context["visit_summary"] = chat_ctx[0]
        context["chat_history"] = chat_ctx[1:]
        
        # Initialize intent identifier and router
        intent_identifier = IntendIdentifierChain()
        intent_router = IntentRouter()
        
        # Identify the intent
        messages = [HumanMessage(content=chat_request.message)]
        intent = intent_identifier.identify_intent(messages)
        # Route the request based on intent
        ai_response = intent_router.route(
            intent=intent,
            text=chat_request.message,
            context=context
        )
                
        # # Store the conversation in Redis
        # redis.rpush(f"conversation:{conversation_id}", chat_request.message)
        # redis.rpush(f"conversation:{conversation_id}", ai_response)
        response = dict()
        response["intent"] = intent
        response["message"] = ai_response
        return response
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        raise e