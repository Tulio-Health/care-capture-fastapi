from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.chat import MedicalChatChain
from src.app.models.provider_visit_summarization import ProviderVisitSummarizationResponse

from ..db.config.database import get_db
from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from src.app.models.chat import ChatRequest
from src.app.cache.redis import redis_client
router = APIRouter(
    prefix="/chat",
    tags=["chat"]
)

redis = redis_client.client

@router.post('/',
             response_model=str,
             status_code=200)
async def chat(chat_request: ChatRequest , db: AsyncSession = Depends(get_db)):
    try:
        conversation_id = chat_request.conversation_id
        chat_ctx = redis.lrange(f"care-capture-cache-key-conversation:{conversation_id}", 0, -1)
        
        if not chat_ctx:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        context = dict()
        context["user_profile"] = "Patient Profile"
        context["visit_summary"] = chat_ctx[0]
        context["chat_history"] = chat_ctx[1:]
        
        chat_chain = MedicalChatChain()
        
        response = chat_chain.chat(input_text=chat_request.message, context=context)
        
        redis.rpush(f"conversation:{conversation_id}", chat_request.message)
        redis.rpush(f"conversation:{conversation_id}", response)
        print(response)
        
        return response
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        raise e