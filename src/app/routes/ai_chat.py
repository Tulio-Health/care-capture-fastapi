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
from src.app.db.models.healthcare_providers import HealthcareProvider
from src.app.models.ai_chat import AiChatRequest
from src.app.models.intent_identify import IntentResponse
from sqlalchemy import select
import json
from src.app.core import get_settings

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
        
        cache_key = CACHE_KEY.CONVERSATION_CHAT_HISTORY.format(conversation_id_str)

        # ADD THESE DEBUG PRINTS:
        settings = get_settings()
        print(f"DEBUG: REDIS HOST: {settings.REDIS_HOST}, PORT: {settings.REDIS_PORT}")
        print(f"DEBUG: conversation_id_str = '{conversation_id_str}'")
        print(f"DEBUG: cache_key = '{cache_key}'")

        raw_messages_from_cache = redis_client.lrange(cache_key, 0, -1)
        
        chat_history_for_context = []
        if raw_messages_from_cache:
            for message_str in raw_messages_from_cache:
                try:
                    parsed_message = json.loads(message_str)
                    if isinstance(parsed_message, list) and len(parsed_message) > 0:
                        ai_response_content = parsed_message[0]
                        if isinstance(ai_response_content, dict) and "content" in ai_response_content:
                            chat_history_for_context.append({"ai_response": ai_response_content["content"]})
                        else:
                            chat_history_for_context.append({"ai_response": str(ai_response_content)})
                    else:
                        chat_history_for_context.append({"unknown_json_format": parsed_message})
                except json.JSONDecodeError:
                    chat_history_for_context.append({"user_query": message_str})
                except Exception as e:
                    print(f"Warning: Error processing message '{message_str}' from cache: {e}")
                    chat_history_for_context.append({"processing_error": message_str})
            
            chat_history_for_context.reverse()
        else:
            print(f"No chat context found in Redis for key: {cache_key}. Assuming new conversation.")

        stmt = select(ChatbotConversation).where(ChatbotConversation.id == chat_request.conversation_id)
        result = await db.execute(stmt)
        conversation_record = result.scalar_one_or_none()

        if not conversation_record:
            raise HTTPException(status_code=404, detail=f"Conversation record not found in database for ID: {conversation_id_str}")

        user_id = conversation_record.user_id
        db_context_summary = conversation_record.context
        
        user_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        user_result = await db.execute(user_stmt)
        user_profile_record = user_result.scalar_one_or_none()
        
        user_profile = {} 
        if user_profile_record:
            user_profile = {
                "id": str(user_profile_record.id),
                "name": f"{user_profile_record.first_name} {user_profile_record.last_name}",
                "phone": user_profile_record.phone_number,
                "dob": user_profile_record.date_of_birth.strftime('%Y-%m-%d') if user_profile_record.date_of_birth else None,
                "language": user_profile_record.preferred_language,
                "is_active": user_profile_record.is_active,
                "zip_code": user_profile_record.zip_code
            }
        else:
            print(f"Warning: No user profile found for user_id: {user_id}")

        context_data = {
            "user_profile": user_profile,
            "visit_summary": db_context_summary, 
            "chat_history": chat_history_for_context 
        }
        
        intent_identifier = IntendIdentifierChain()
        intent_router = IntentRouter(db=db)
        
        messages = [HumanMessage(content=chat_request.message)]
        intent = intent_identifier.identify_intent(messages)
        
        if intent == RouterOptions.PAST_VISITS.value:
            user_id_for_appt = str(user_id)
            appointments_stmt = select(Appointment).where(Appointment.user_id == user_id_for_appt)
            appointments_result = await db.execute(appointments_stmt)
            appointments = appointments_result.scalars().all()
            
            formatted_appointments = []
            provider_ids = set()
            
            for appt in appointments:
                formatted_appt = {
                    "id": str(appt.id),
                    "date": appt.appointment_date.isoformat() if appt.appointment_date else None,
                    "time": appt.appointment_time.strftime('%H:%M:%S') if appt.appointment_time else None,
                    "duration": appt.duration_minutes,
                    "purpose": appt.purpose,
                    "location": appt.location,
                    "status": appt.status,
                    "provider_id": str(appt.provider_id) if appt.provider_id else None,
                }
                formatted_appointments.append(formatted_appt)
                if appt.provider_id:
                    provider_ids.add(appt.provider_id)
            
            context_data["appointments"] = formatted_appointments
            
            providers_data = []
            if provider_ids:
                providers_stmt = select(HealthcareProvider).where(HealthcareProvider.id.in_(provider_ids))
                providers_result = await db.execute(providers_stmt)
                providers_db = providers_result.scalars().all()
                providers_data = [
                    {
                        "id": str(provider.id),
                        "name": provider.name,
                        "specialty": provider.specialty,
                        "location": f"{provider.address}, {provider.city}, {provider.state} {provider.postal_code}",
                        "contact": provider.phone_number
                    }
                    for provider in providers_db
                ]
            context_data["healthcare_providers"] = providers_data
        
        print(f"Intent identified: {intent}")
        print(f"Context data keys: {list(context_data.keys())}")
        
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