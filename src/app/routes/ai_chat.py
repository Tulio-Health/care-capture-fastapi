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
from src.app.models.ai_chat import AiChatRequest
from src.app.models.intent_identify import IntentResponse, MedicalIntentResponse
from sqlalchemy import select
import json
from src.app.core import get_settings
from src.app.routes.pull_db_context import cache_user_profile_and_insights, read_enriched_summaries
from src.app.common.constants.cache_keys import chatbot_conversation_context_key
from typing import Union

router = APIRouter(
    prefix="/care-capture/ai-chat",
    tags=["care-capture-ai-chat"]
)

@router.post('/',
             response_model=Union[IntentResponse, MedicalIntentResponse],
             status_code=200)
async def ai_chat(chat_request: AiChatRequest, db: AsyncSession = Depends(get_db)):
    try:
        conversation_id = chat_request.conversation_id
        # To ensure it's being received properly, and add validation:
        user_id = chat_request.user_id
        # user_id = "58ae6e54-c712-4900-bc02-f80a2f2d9e85" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.
        # user_id = "2a14bdf4-a39c-45fa-b76e-5972860603ec" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.
        # user_id = "0ca4bb1b-6233-48fd-9998-99f556cdc22a" # HARDCODED (I don't know how user id is fetched). TODO: Remove this.
        
        # --- Load user profile and health insights (FastAPI-managed cache) ---
        user_profile_key = CACHE_KEY.CONVERSATION_USER_PROFILE.format(user_id)
        health_insights_key = CACHE_KEY.CONVERSATION_HEALTH_INSIGHTS.format(user_id)
        conversation_messages_key = CACHE_KEY.CONVERSATION_CHAT_HISTORY.format(conversation_id)

        try:
            user_profile = json.loads(redis_client.get(user_profile_key))
        except Exception:
            user_profile = None

        try:
            health_insights = json.loads(redis_client.get(health_insights_key))
        except Exception:
            health_insights = None

        # Repopulate profile/insights if missing
        if not user_profile or not health_insights:
            await cache_user_profile_and_insights(db, user_id, redis_client)
            try:
                user_profile = json.loads(redis_client.get(user_profile_key))
            except Exception:
                user_profile = {}
            try:
                health_insights = json.loads(redis_client.get(health_insights_key))
            except Exception:
                health_insights = []

        # --- Read enriched summaries from Node API cache ---
        enriched_summaries = read_enriched_summaries(user_id, redis_client)
        if enriched_summaries is None:
            enriched_summaries = []
            print(f"Warning: No enriched summary cache for user {user_id}. Node API has not populated it yet.")

        # --- Load conversation messages (managed by Node API) ---
        # Keep last 30 items (≈15 user+AI pairs) to bound context size
        MAX_CONVERSATION_ITEMS = 30
        raw_conversation_history_items = redis_client.lrange(conversation_messages_key, -MAX_CONVERSATION_ITEMS, -2)
        conversation_messages = []
        if raw_conversation_history_items:
            for item_str in raw_conversation_history_items:
                try:
                    parsed_item = json.loads(item_str)
                    conversation_messages.append(parsed_item)
                except json.JSONDecodeError:
                    conversation_messages.append(item_str)

        # --- Load conversation context for follow-ups ---
        conversation_context = {}
        try:
            ctx_key = chatbot_conversation_context_key(conversation_id)
            raw_ctx = redis_client.get(ctx_key)
            if raw_ctx:
                conversation_context = json.loads(raw_ctx)
        except Exception:
            conversation_context = {}

        # Build context data
        context_data = {
            "user_profile": user_profile,
            "enriched_summaries": enriched_summaries,
            "conversation_messages": conversation_messages,
            "health_insights": health_insights,
            "conversation_context": conversation_context,
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