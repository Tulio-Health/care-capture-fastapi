from click import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from src.app.cache.redis import redis_client
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.chains.ai_chat_intents.intend_identifier.chain import IntendIdentifierChain
from src.app.chains.ai_chat_intents.intend_identifier.router import IntentRouter
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.db.config.database import get_db
from src.app.db.models.chatbot_conversations import ChatbotConversation
from src.app.db.models.chatbot_messages import ChatbotMessage
from src.app.db.models.user_profiles import UserProfile
from src.app.db.models.appointments import Appointment
from src.app.models.ai_chat import AiChatRequest
from src.app.models.intent_identify import IntentResponse
from sqlalchemy import select
import json
from src.app.core import get_settings
from src.app.routes.pull_db_context import cache_all_user_data

router = APIRouter(
    prefix="/care-capture/ai-chat",
    tags=["care-capture-ai-chat"]
)

@router.post('/',
             response_model=IntentResponse,
             status_code=200)
async def ai_chat(chat_request: AiChatRequest, db: AsyncSession = Depends(get_db)):
    print(f"Chat request: {chat_request}")
    try:
        conversation_id_str = str(chat_request.conversation_id)
        stmt = select(ChatbotConversation).where(ChatbotConversation.id == chat_request.conversation_id)
        result = await db.execute(stmt)
        conversation_record = result.scalar_one_or_none()
        if not conversation_record:
            raise HTTPException(status_code=404, detail=f"Conversation record not found in database for ID: {conversation_id_str}")
        user_id = conversation_record.user_id
        user_id = UUID("58ae6e54-c712-4900-bc02-f80a2f2d9e85")  # HARDCODED FOR TESTING
        
        # Set up cache keys
        user_profile_key = f"user_profile:{user_id}"
        appointments_key = f"appointments:{user_id}"
        visit_summaries_key = f"visit_summaries:{user_id}"
        conversation_messages_key = f"conversation_messages:{user_id}"
        
        # Check if all required cache keys exist
        cache_miss = False
        if not redis_client.get(user_profile_key):
            print(f"Cache miss: user_profile for user_id={user_id}")
            cache_miss = True
        if not redis_client.get(appointments_key):
            print(f"Cache miss: appointments for user_id={user_id}")
            cache_miss = True
        if not redis_client.get(visit_summaries_key):
            print(f"Cache miss: visit_summaries for user_id={user_id}")
            cache_miss = True
        if not redis_client.get(conversation_messages_key):
            print(f"Cache miss: conversation_messages for user_id={user_id}")
            cache_miss = True
            
        # Populate cache if any key is missing
        if cache_miss:
            print(f"Repopulating cache for user_id={user_id}")
            await cache_all_user_data(db, user_id, redis_client)
            
        # Always load from cache
        try:
            user_profile = json.loads(redis_client.get(user_profile_key))
            appointments = json.loads(redis_client.get(appointments_key))
            visit_summaries = json.loads(redis_client.get(visit_summaries_key))
            conversation_messages = json.loads(redis_client.get(conversation_messages_key))
        except Exception as e:
            print(f"Error loading from cache: {str(e)}")
            # If there's an error loading from cache, refresh the cache and try again
            await cache_all_user_data(db, user_id, redis_client)
            user_profile = json.loads(redis_client.get(user_profile_key))
            appointments = json.loads(redis_client.get(appointments_key))
            visit_summaries = json.loads(redis_client.get(visit_summaries_key))
            conversation_messages = json.loads(redis_client.get(conversation_messages_key))
            
        # Build context data
        context_data = {
            "user_profile": user_profile,
            "appointments": appointments,
            "visit_summaries": visit_summaries,
            "conversation_messages": conversation_messages
        }
        
        # Process the chat request
        intent_identifier = IntendIdentifierChain()
        intent_router = IntentRouter(db=db)
        messages = [HumanMessage(content=chat_request.message)]
        intent = intent_identifier.identify_intent(messages)
        ai_response = await intent_router.route(
            intent=intent,
            text=chat_request.message,
            context=context_data, 
            conversation_id=conversation_id_str
        )
        return ai_response
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))