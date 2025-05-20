from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from src.app.chains.ai_chat_intents.intend_identifier.chain import IntendIdentifierChain
from src.app.chains.ai_chat_intents.intend_identifier.router import IntentRouter
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.models.intent_identify import IntentResponse

from ..db.config.database import get_db
from src.app.models.ai_chat import AiChatRequest
# Remove Redis import as we are not using it here for fetching
# from src.app.cache.redis import redis_client

# Import select for SQLAlchemy query
from sqlalchemy import select

# Import the ORM models
from src.app.db.models.chatbot_conversations import ChatbotConversation
from src.app.db.models.chatbot_messages import ChatbotMessage
from src.app.db.models.user_profiles import UserProfile
from src.app.db.models.appointments import Appointment
from src.app.db.models.healthcare_providers import HealthcareProvider

router = APIRouter(
    prefix="/care-capture/ai-chat",
    tags=["care-capture-ai-chat"]
)

# redis = redis_client.client # Not needed for this approach

@router.post('/',
             response_model=IntentResponse,
             status_code=200)
async def ai_chat(chat_request: AiChatRequest, db: AsyncSession = Depends(get_db)):
    print(f"Chat request: {chat_request}")
    try:
        conversation_id = chat_request.conversation_id
        
        # Fetch conversation context from the database using ORM model
        stmt = select(ChatbotConversation).where(ChatbotConversation.id == conversation_id)
        result = await db.execute(stmt)
        conversation_record = result.scalar_one_or_none()

        if not conversation_record:
            raise HTTPException(status_code=404, detail="Conversation not found in database")

        # Use the ORM object's attributes
        db_context_summary = conversation_record.context
        
        # Fetch user information using user_id from conversation record
        user_id = conversation_record.user_id
        # Query the user_profiles table where user_id column matches the user_id from conversation
        user_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        user_result = await db.execute(user_stmt)
        user_profile_record = user_result.scalar_one_or_none()
        
        # Format user profile information
        user_profile = "Patient Profile"  # Default fallback
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
        
        # Fetch messages for the specific conversation_id
        messages_stmt = select(ChatbotMessage).where(ChatbotMessage.conversation_id == conversation_id)
        messages_result = await db.execute(messages_stmt)
        db_chat_history = messages_result.scalars().all()  # Get all messages

        # Prepare the chat history in the desired format
        formatted_chat_history = [
            {
                "user_query": msg.user_query,
                "ai_response": msg.ai_response,
                "detected_intent": msg.detected_intent,
                "created_at": msg.created_at,
                "updated_at": msg.updated_at
            }
            for msg in db_chat_history
        ]

        context_data = {
            "user_profile": user_profile,
            "visit_summary": db_context_summary,
            "chat_history": formatted_chat_history
        }
        
        # Initialize intent identifier and router
        intent_identifier = IntendIdentifierChain()
        intent_router = IntentRouter()
        
        # Identify the intent
        messages = [HumanMessage(content=chat_request.message)]
        intent = intent_identifier.identify_intent(messages)
        
        # If the intent is past_visit, fetch all appointments for the user
        if intent == RouterOptions.PAST_VISITS.value:
            # Fetch all appointments for this user
            # Convert UUID to string when querying since user_id is stored as string in the database
            user_id_str = str(user_id)
            appointments_stmt = select(Appointment).where(Appointment.user_id == user_id_str)
            appointments_result = await db.execute(appointments_stmt)
            appointments = appointments_result.scalars().all()
            
            # Format appointments for the context (we're not getting all data)
            formatted_appointments = []
            provider_ids = set()  # Collect unique provider IDs
            
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
                
                # Add provider ID to the set if it exists
                if appt.provider_id:
                    provider_ids.add(appt.provider_id)
            
            # Add appointments to the context data 
            context_data["appointments"] = formatted_appointments
            
            # Fetch healthcare providers data for all providers in appointments
            providers = []
            if provider_ids:
                providers_stmt = select(HealthcareProvider).where(HealthcareProvider.id.in_(provider_ids))
                providers_result = await db.execute(providers_stmt)
                providers_db = providers_result.scalars().all()
                
                # Format provider information
                providers = [
                    {
                        "id": str(provider.id),
                        "name": provider.name,
                        "specialty": provider.specialty,
                        "location": f"{provider.address}, {provider.city}, {provider.state} {provider.postal_code}",
                        "contact": provider.phone_number
                    }
                    for provider in providers_db
                ]
                
                # Add providers to the context data
                context_data["healthcare_providers"] = providers
        
        # Route the request based on intent
        print(f"Intent identified: {intent}")
        print(f"Context data keys: {context_data.keys()}")
        print(f"Context data user_profile: {context_data.get('user_profile', {})}")
        print(f"Context data visit_summary: {context_data.get('visit_summary', '')}")
        print(f"Context data appointments count: {len(context_data.get('appointments', []))}")
        print(f"Context data healthcare_providers count: {len(context_data.get('healthcare_providers', []))}")
        
        ai_response = intent_router.route(
            intent=intent,
            text=chat_request.message,
            context=context_data, # Pass the modified context_data
            conversation_id=conversation_id
        )

        return ai_response
    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        raise e