import logging
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
import json

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.core import get_settings
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.cache.redis import redis_client
from src.app.db.config.database import get_db
from src.app.routes.pull_db_context import cache_all_user_data
from src.app.chains.ai_chat_intents.medical_inquiry_intent.constants import (
    MEDICAL_INQUIRY_SYSTEM_PROMPT,
    MEDICAL_INQUIRY_USER_PROMPT
)
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

logger = logging.getLogger(__name__)


MedicalInquiryResponse = IntentResponse[None]

class MedicalInquiryIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=MedicalInquiryResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", MEDICAL_INQUIRY_SYSTEM_PROMPT),
            ("user", MEDICAL_INQUIRY_USER_PROMPT)
        ])
        self.chain = self.prompt | model | self.parser

    async def handle_intent(self, **kwargs) -> MedicalInquiryResponse:
        try:
            text = kwargs['text']
            user_id = kwargs.get('user_id')
            
            # Get cached context data
            user_profile, health_insights = await self._get_cached_context(user_id)
            
            response = self.chain.invoke({
                "text": text, 
                "user_profile": user_profile,
                "health_insights": health_insights,
                "output_format": self.parser.get_format_instructions()
            })
            return response
        except Exception as e:
            logger.error(f"Error processing medical inquiry: {str(e)}")
            return MedicalInquiryResponse(
                intent=RouterOptions.MEDICAL_INQUIRY, 
                responses=[IntentAiResponse(
                    type="text", 
                    content="I apologize, but I couldn't process your medical inquiry. It is advisable to consult your PCP or a specialist.", 
                    data=None)])

    async def _get_cached_context(self, user_id: str) -> tuple[str, str]:
        """Get cached user profile and health insights data"""
        try:
            if not user_id:
                return "No user profile available", "No health insights available"
            
            # Try to get cached data
            user_profile_key = CACHE_KEY.CONVERSATION_USER_PROFILE.format(user_id)
            health_insights_key = CACHE_KEY.CONVERSATION_HEALTH_INSIGHTS.format(user_id)
            
            user_profile_data = redis_client.get(user_profile_key)
            health_insights_data = redis_client.get(health_insights_key)
            
            # If cache miss, populate cache
            if not user_profile_data or not health_insights_data:
                logger.info(f"Cache miss for medical inquiry context, user_id={user_id}")
                async for db in get_db():
                    await cache_all_user_data(db, user_id, None, redis_client)
                    break
                
                # Retry getting cached data
                user_profile_data = redis_client.get(user_profile_key)
                health_insights_data = redis_client.get(health_insights_key)
            
            # Parse cached data
            user_profile = json.loads(user_profile_data) if user_profile_data else {}
            health_insights = json.loads(health_insights_data) if health_insights_data else []
            
            # Format for prompt
            user_profile_str = self._format_user_profile(user_profile)
            health_insights_str = self._format_health_insights(health_insights)
            
            return user_profile_str, health_insights_str
            
        except Exception as e:
            logger.error(f"Error getting cached context: {str(e)}")
            return "No user profile available", "No health insights available"

    def _format_user_profile(self, profile: dict) -> str:
        """Format user profile for prompt context"""
        if not profile:
            return "No user profile available"
        
        formatted = []
        if profile.get('name'):
            formatted.append(f"Name: {profile['name']}")
        if profile.get('dob'):
            formatted.append(f"Date of Birth: {profile['dob']}")
        if profile.get('language'):
            formatted.append(f"Preferred Language: {profile['language']}")
        
        return "; ".join(formatted) if formatted else "Limited profile information available"

    def _format_health_insights(self, insights: list) -> str:
        """Format health insights for prompt context"""
        if not insights:
            return "No health insights available"
        
        formatted_insights = []
        for insight in insights:
            insight_data = insight.get('insight_data', {})
            if isinstance(insight_data, dict):
                # Extract key information from insight data
                conditions = insight_data.get('conditions', [])
                medications = insight_data.get('medications', [])
                
                insight_summary = []
                if conditions:
                    condition_names = [c.get('name', '') for c in conditions if c.get('name')]
                    if condition_names:
                        insight_summary.append(f"Conditions: {', '.join(condition_names[:3])}")
                
                if medications:
                    med_names = [m.get('name', '') for m in medications if m.get('name')]
                    if med_names:
                        insight_summary.append(f"Medications: {', '.join(med_names[:3])}")
                
                if insight_summary:
                    formatted_insights.append("; ".join(insight_summary))
        
        return "; ".join(formatted_insights) if formatted_insights else "No specific health insights available"