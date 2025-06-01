from uuid import UUID
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
    try:
        conversation_id = chat_request.conversation_id
        # To ensure it's being received properly, and add validation:
        user_id = chat_request.user_id
        user_id = "58ae6e54-c712-4900-bc02-f80a2f2d9e85" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.
        # user_id = "2a14bdf4-a39c-45fa-b76e-5972860603ec" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.

        # user_id = "0ca4bb1b-6233-48fd-9998-99f556cdc22a" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.
        
        # Set up cache keys
        user_profile_key = CACHE_KEY.CONVERSATION_USER_PROFILE.format(user_id)
        appointments_key = CACHE_KEY.CONVERSATION_PAST_APPOINTMENTS.format(user_id)
        visit_summaries_key = CACHE_KEY.CONVERSATION_PROVIDER_VISIT_SUMMARY.format(user_id)
        conversation_messages_key = CACHE_KEY.CONVERSATION_CHAT_HISTORY.format(conversation_id)
        health_insights_key = CACHE_KEY.CONVERSATION_HEALTH_INSIGHTS.format(user_id)
        
        # Check if required cache keys exist
        cache_miss = False
        
        try:
            user_profile = json.loads(redis_client.get(user_profile_key))
        except Exception as e:
            user_profile = None
        
        try:
            appointments = json.loads(redis_client.get(appointments_key))
        except Exception as e:
            appointments = None
        
        try:
            visit_summaries = json.loads(redis_client.get(visit_summaries_key)) 
        except Exception as e:    
            visit_summaries = None
            
        try:
            health_insights = json.loads(redis_client.get(health_insights_key))
        except Exception as e:
            health_insights = None
        
        if not user_profile or not appointments or not visit_summaries or not health_insights:
            print(f"Cache miss: user_profile, appointments, visit_summaries, or health_insights for user_id={user_id}")
            cache_miss = True
            
        if cache_miss:
            print(f"Repopulating cache for user_id={user_id} (excluding messages)")
            await cache_all_user_data(db, user_id, conversation_id, redis_client)
            user_profile = json.loads(redis_client.get(user_profile_key))
            appointments = json.loads(redis_client.get(appointments_key))
            visit_summaries = json.loads(redis_client.get(visit_summaries_key))
            health_insights = json.loads(redis_client.get(health_insights_key))

        # Load conversation messages using lrange from its specific key, handled by Node API
        # This is done once, outside the try/except for primary context loading.
        raw_conversation_history_items = redis_client.lrange(conversation_messages_key, 0, -2)
        conversation_messages = []
        if raw_conversation_history_items:
            for item_str in raw_conversation_history_items:
                try:
                    # Attempt to parse each item as JSON
                    # If successful, it could be a dict (like AI response obj) or a list (like summary snapshot)
                    parsed_item = json.loads(item_str)
                    conversation_messages.append(parsed_item)
                except json.JSONDecodeError:
                    # If it's not valid JSON (e.g., plain user query string), append as is
                    conversation_messages.append(item_str)
        
        # Build context data
        context_data = {
            "user_profile": user_profile,
            "appointments": appointments,
            "visit_summaries": visit_summaries,
            "conversation_messages": conversation_messages,
            "health_insights": health_insights
        }
        
        # Process the chat request
        intent_identifier = IntendIdentifierChain()
        intent_router = IntentRouter(db=db)
        intent = intent_identifier.identify_intent(conversation_messages, chat_request.message)
        ai_response = await intent_router.route(
            intent=intent,
            text=chat_request.message,
            context=context_data, 
            conversation_id=conversation_id,
            user_id=user_id
        )
        print("AI response: ", ai_response)
        return ai_response
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))