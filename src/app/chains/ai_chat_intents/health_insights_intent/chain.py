import logging
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.common.constants.llm import LLM_MODEL , LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.db.config.database import get_db
from src.app.db.objects.entities.patient_health_insights import PatientHealthInsights
from src.app.db.objects.repositories.patient_health_insights import PatientHealthInsightsRepository
from src.app.models.intent_identify import IntentResponse
from src.app.cache.redis import redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder


from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.chains.ai_chat_intents.health_insights_intent.constants import (
    HEALTH_INSIGHTS_SYSTEM_PROMPT,
    HEALTH_INSIGHTS_USER_PROMPT
)
from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)
tracer = LangSmithTrace().trace(tags=[__name__])


logger = logging.getLogger(__name__)

HealthInsightsExtractionResponse = IntentResponse[None]

class HealthInsightsIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsExtractionResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", HEALTH_INSIGHTS_SYSTEM_PROMPT),
            ("user", HEALTH_INSIGHTS_USER_PROMPT)
        ])
        self.chain = self.prompt | model | self.parser

    async def handle_intent(self, **kwargs) -> HealthInsightsExtractionResponse:
        try:
            text = kwargs['text']
            context = kwargs.get('context', {})
            
            # Get data directly from context instead of fetching from cache
            user_profile = context.get('user_profile', {})
            health_insights = context.get('health_insights', [])
            
            # Format context data for prompt
            user_profile_str = self._format_user_profile(user_profile)
            health_insights_str = self._format_health_insights(health_insights)
            
            response = self.chain.invoke({
                "text": text, 
                "user_profile": user_profile_str,
                "health_insights": health_insights_str,
                "output_format": self.parser.get_format_instructions()
            })
            return response
        except Exception as e:
            logger.error(f"Error processing health insights inquiry: {str(e)}")
            return HealthInsightsExtractionResponse(
                intent=RouterOptions.HEALTH_INSIGHTS, 
                responses=[IntentAiResponse(
                    type="text", 
                    content="I apologize, but I couldn't access your health insights at the moment. Please try again later or consult with your healthcare provider.", 
                    data=None)])

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
        """Format health insights for prompt context with detailed information"""
        if not insights:
            return "No health insights available"
        
        formatted_insights = []
        for insight in insights:
            insight_data = insight.get('insight_data', {})
            if isinstance(insight_data, dict):
                insight_parts = []
                
                # Extract detailed information from insight data
                conditions = insight_data.get('conditions', [])
                medications = insight_data.get('medications', [])
                surgeries = insight_data.get('surgeriesAndProcedures', [])
                prior_testing = insight_data.get('priorTesting', [])
                
                if conditions:
                    condition_details = []
                    for condition in conditions:
                        name = condition.get('name', '')
                        details = condition.get('details', '')
                        date = condition.get('date', '')
                        condition_str = name
                        if details:
                            condition_str += f" ({details})"
                        if date:
                            condition_str += f" - {date}"
                        condition_details.append(condition_str)
                    insight_parts.append(f"Conditions: {'; '.join(condition_details)}")
                
                if medications:
                    med_details = []
                    for med in medications[:5]:  # Limit to 5 most recent
                        name = med.get('name', '')
                        dosage = med.get('dosage', '')
                        frequency = med.get('frequency', '')
                        date = med.get('date', '')
                        med_str = name
                        if dosage:
                            med_str += f" {dosage}"
                        if frequency:
                            med_str += f" ({frequency})"
                        if date:
                            med_str += f" - {date}"
                        med_details.append(med_str)
                    insight_parts.append(f"Medications: {'; '.join(med_details)}")
                
                if surgeries:
                    surgery_details = []
                    for surgery in surgeries:
                        name = surgery.get('name', '')
                        details = surgery.get('details', '')
                        date = surgery.get('date', '')
                        surgery_str = name
                        if details:
                            surgery_str += f" ({details})"
                        if date:
                            surgery_str += f" - {date}"
                        surgery_details.append(surgery_str)
                    insight_parts.append(f"Surgeries/Procedures: {'; '.join(surgery_details)}")
                
                if prior_testing:
                    test_details = []
                    for test in prior_testing:
                        name = test.get('name', '')
                        result = test.get('result', '')
                        date = test.get('date', '')
                        test_str = name
                        if result:
                            test_str += f" (Result: {result})"
                        if date:
                            test_str += f" - {date}"
                        test_details.append(test_str)
                    insight_parts.append(f"Prior Testing: {'; '.join(test_details)}")
                
                if insight_parts:
                    formatted_insights.append(" | ".join(insight_parts))
        
        return " || ".join(formatted_insights) if formatted_insights else "No specific health insights available"
    
    async def fetch_health_insights(self, user_id: str ) -> str:
        async for session in get_db():
            repo = PatientHealthInsightsRepository(session)
            health_insights = await repo.get_by_user_id(user_id)
            return jsonable_encoder(health_insights)
    
    def invoke(self, text: str, context: str) -> HealthInsightsExtractionResponse:
        return self.chain.invoke({"text": text ,"context":context , "output_format": self.parser.get_format_instructions()}, config={"callbacks": [tracer]})
