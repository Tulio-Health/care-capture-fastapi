import logging
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
import json

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.core import get_settings
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.chains.ai_chat_intents.medical_inquiry_intent.constants import (
    MEDICAL_INQUIRY_SYSTEM_PROMPT,
    MEDICAL_INQUIRY_USER_PROMPT
)

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

logger = logging.getLogger(__name__)


class MedicalInquiryIntentChain:
    def __init__(self):
        # Use StrOutputParser for natural text responses like past visit chain
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", MEDICAL_INQUIRY_SYSTEM_PROMPT),
            ("user", MEDICAL_INQUIRY_USER_PROMPT)
        ])
        # Chain for generating natural text content
        self.chain = self.prompt | model | StrOutputParser()

    async def handle_intent(self, **kwargs) -> IntentResponse[None]:
        try:
            text = kwargs['text']
            context = kwargs.get('context', {})
            
            # Extract user profile and conversation history from context
            user_profile = context.get('user_profile', {})
            # Use 'conversation_messages' key for consistency with ai_chat.py
            chat_history = context.get('conversation_messages', [])
            # Get health insights directly from context instead of fetching from cache
            health_insights = context.get('health_insights', [])
            
            # Format context data for prompt
            user_profile_str = self._format_user_profile(user_profile)
            health_insights_str = self._format_health_insights(health_insights)
            
            # Generate natural text response
            ai_content_string = await self.chain.ainvoke({
                "text": text, 
                "user_profile": user_profile_str,
                "health_insights": health_insights_str,
                "conversation_history": json.dumps(chat_history, default=str)
            })
            
            # Return the response in the expected format
            return IntentResponse[None](
                intent=RouterOptions.MEDICAL_INQUIRY,
                responses=[IntentAiResponse(
                    type="text", 
                    content=ai_content_string, 
                    data=None
                )]
            )
            
        except Exception as e:
            logger.error(f"Error processing medical inquiry: {str(e)}")
            return IntentResponse[None](
                intent=RouterOptions.MEDICAL_INQUIRY, 
                responses=[IntentAiResponse(
                    type="text", 
                    content="I apologize, but I couldn't process your medical inquiry. It is advisable to consult your PCP or a specialist.", 
                    data=None
                )]
            )

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
                # Extract comprehensive information from insight data
                conditions = insight_data.get('conditions', [])
                medications = insight_data.get('medications', [])
                prior_testing = insight_data.get('priorTesting', [])
                surgeries = insight_data.get('surgeriesAndProcedures', [])
                
                insight_summary = []
                
                # Format conditions with details
                if conditions:
                    condition_details = []
                    for c in conditions[:5]:  # Limit to 5 most recent
                        if c.get('name'):
                            detail = c['name']
                            if c.get('details'):
                                detail += f" ({c['details']})"
                            condition_details.append(detail)
                    if condition_details:
                        insight_summary.append(f"Conditions: {', '.join(condition_details)}")
                
                # Format medications with dosage
                if medications:
                    med_details = []
                    for m in medications[:5]:  # Limit to 5 most recent
                        if m.get('name'):
                            detail = m['name']
                            if m.get('dosage'):
                                detail += f" {m['dosage']}"
                            if m.get('frequency'):
                                detail += f" {m['frequency']}"
                            med_details.append(detail)
                    if med_details:
                        insight_summary.append(f"Medications: {', '.join(med_details)}")
                
                # Format prior testing
                if prior_testing:
                    test_names = [t.get('name', '') for t in prior_testing[:3] if t.get('name')]
                    if test_names:
                        insight_summary.append(f"Recent Testing: {', '.join(test_names)}")
                
                # Format surgeries/procedures
                if surgeries:
                    surgery_names = [s.get('name', '') for s in surgeries[:3] if s.get('name')]
                    if surgery_names:
                        insight_summary.append(f"Procedures: {', '.join(surgery_names)}")
                
                if insight_summary:
                    formatted_insights.append("; ".join(insight_summary))
        
        return "; ".join(formatted_insights) if formatted_insights else "No specific health insights available"