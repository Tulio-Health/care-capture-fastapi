from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from datetime import date, datetime

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.models.past_visit_query import PastVisitQuery
from src.app.models.conversation_summaries import ConversationSummary as PydanticConversationSummary
from src.app.db.objects.entities.conversation_summaries import ConversationSummaries as ORMConversationSummaries
from src.app.core import get_settings
from .constants import QUERY_PROMPT, RESPONSE_PROMPT

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

tracer = LangSmithTrace().trace(tags=[__name__])


NO_PAST_VISIT_INFORMATION_AVAILABLE = "I am sorry, but I don't have any past Provider visit information available for you, please try with a different query."

class PastVisitIntentChain:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Initialize output parser for query parameters
        self.query_parser = PydanticOutputParser(pydantic_object=PastVisitQuery)
        
        # First prompt: Extract structured query parameters
        self.query_prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_PROMPT),
            ("user", "Generate the query parameters for the following user question: {text}\n"
                      "**Conversation History** (`{conversation_history}`): Previous messages in this conversation. "
                      "Use this intelligently to understand the natural flow of conversation. The user might reference "
                      "previous topics, ask follow-up questions, or build upon earlier discussions. Be contextually aware "
                      "and extract relevant information that helps clarify the current query.")
        ])
        
        # Today's date in ISO format
        today_date = date.today().isoformat()

        # Second prompt: Generate the final response based on filtered appointments
        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", RESPONSE_PROMPT),
            ("user", "User Original Question: {text}\nConversation History: {conversation_history}\nFiltered Appointments: {filtered_appointments}\nHealthcare Provider Details: {providers_info}\nConversation Summaries: {conversation_summaries}\nToday's Date: {today_date}")
        ])
        
        # Chain for query extraction
        self.query_chain = self.query_prompt | model | self.query_parser
        
        # Chain for final response content generation
        self.response_content_chain = self.response_prompt | model | StrOutputParser()

    def filter_appointments(self, query: PastVisitQuery, appointments: List[Dict[str, Any]], providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter appointments based on the query parameters
        """
        # Start with all appointments
        filtered = appointments
        
        # Apply filters based on query parameters
        if query.provider_id:
            filtered = [appt for appt in filtered if appt.get('provider_id') == query.provider_id]
        
        if query.provider_name and providers:
            # Find provider_id matching the name
            provider_ids = [p['id'] for p in providers if query.provider_name.lower() in p.get('name', '').lower()]
            if provider_ids:
                filtered = [appt for appt in filtered if appt.get('provider_id') in provider_ids]
        
        if query.purpose:
            filtered = [appt for appt in filtered if query.purpose.lower() in appt.get('purpose', '').lower()]
            
        if query.location and providers:
            # First find providers that match the location
            matching_provider_ids = []
            for provider in providers:
                # The location field is now a composite of address, city, state, postal_code
                provider_location = provider.get('location', '').lower()
                if query.location.lower() in provider_location:
                    matching_provider_ids.append(provider['id'])
            
            # Then filter appointments by those provider IDs
            if matching_provider_ids:
                filtered = [appt for appt in filtered if appt.get('provider_id') in matching_provider_ids]
            else:
                # If no provider matches, try to match on appointment location
                filtered = [appt for appt in filtered if query.location.lower() in appt.get('location', '').lower()]
        
        # Apply date filters
        today = date.today()
        today_iso = today.isoformat()  # Get today's date in ISO format
        
        # Define how we'll filter based on timeframe
        if query.timeframe == 'specific_date' and query.start_date:
            # For specific date, only show appointments on that exact date
            filtered = [appt for appt in filtered if appt.get('date') == query.start_date.isoformat()]
        elif query.timeframe == 'date_range' and query.start_date:
            # For date range, calculate appropriate end date
            end_date = today_iso
            if query.end_date and query.end_date.isoformat() <= today_iso:
                end_date = query.end_date.isoformat()
            
            filtered = [appt for appt in filtered if 
                       query.start_date.isoformat() <= appt.get('date', '') <= end_date]
        else:
            # Default case (including when timeframe is 'all'): only pick appointments from the past
            filtered = [appt for appt in filtered if appt.get('date', '') <= today_iso]
        
        # Sort the results
        if query.sort_by == 'date':
            filtered.sort(key=lambda x: x.get('date', ''), reverse=(query.sort_order == 'desc'))
        elif query.sort_by == 'provider':
            filtered.sort(key=lambda x: x.get('provider_id', ''), reverse=(query.sort_order == 'desc'))
        
        # Apply limit if specified
        if query.limit and len(filtered) > query.limit:
            filtered = filtered[:query.limit]
            
        return filtered
    
    def get_providers_info(self, provider_ids: List[str], providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get information about providers mentioned in the filtered appointments
        """
        return [p for p in providers if p.get('id') in provider_ids]


    @traceable(name="handle_intent")
    async def handle_intent(self, **kwargs) -> IntentResponse[None]:
        text = kwargs['text']
        context = kwargs['context']

        user_profile = context.get('user_profile', {})
        # Use 'conversation_messages' key for consistency with ai_chat.py
        chat_history = context.get('conversation_messages', []) 
        user_id = user_profile.get('id')

        # Get appointments directly from the passed context
        appointments = context.get('appointments', [])
        # If no appointment data is available
        if not appointments:
            print("No appointments found in context")
            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(type="text", content=NO_PAST_VISIT_INFORMATION_AVAILABLE, data=None)]
            )

        appointment_keys = list(appointments[0].keys()) if appointments else []

        try:
            print(f"Extracting query parameters for query: {text}")
            query_params = self.query_chain.invoke({
                "text": text,
                "user_profile": json.dumps(user_profile, default=str),
                "appointment_keys": json.dumps(appointment_keys),
                "appointments_data": json.dumps(appointments, default=str),
                "conversation_history": json.dumps(chat_history, default=str),
                "query_format": self.query_parser.get_format_instructions()
            } , config={"callbacks": [tracer]})

            print(f"Extracted queryy parameters: {query_params}")

            # Step 2: Filter appointments based on query
            filtered_appointments = self.filter_appointments(query_params, appointments, [])
            print(f"Found {len(filtered_appointments)} relevant appointments")

            # Get all visit summaries from context
            all_visit_summaries = context.get('visit_summaries', [])
            
            # Filter summaries relevant to the filtered_appointments
            appointment_ids_for_summaries_set = set(str(appt.get('id')) for appt in filtered_appointments if appt.get('id'))
            relevant_summaries = [
                summary for summary in all_visit_summaries
                if summary.get('appointment_id') and str(summary.get('appointment_id')) in appointment_ids_for_summaries_set
            ]
            print(f"Found {len(relevant_summaries)} relevant summaries from context for the filtered appointments")

            # Step 3: Generate final response
            if not filtered_appointments and not relevant_summaries:
                return IntentResponse[None](
                    intent="past_visits",
                    responses=[IntentAiResponse(
                        type="text", 
                        content="I'm sorry, but I couldn't find any past visits or related summaries matching your criteria.", #TODO: Add a more specific message related to the query. Extra LLM call to generate a more specific message.
                        data=None
                    )]
                )

            ai_content_string = await self.response_content_chain.ainvoke({
                "text": text,
                "conversation_history": json.dumps(chat_history, default=str),
                "filtered_appointments": json.dumps(filtered_appointments, default=str),
                "providers_info": json.dumps([], default=str),
                "conversation_summaries": json.dumps(relevant_summaries, default=str),
                "today_date": date.today().isoformat()
            },config={"callbacks": [tracer]})

            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(type="text", content=ai_content_string, data=None)]
            )

        except Exception as e:
            print(f"Error processing past visit query: {str(e)}")
            import traceback
            traceback.print_exc()
            fallback_content = NO_PAST_VISIT_INFORMATION_AVAILABLE
            print(f"Falling back. Content: {fallback_content}")
            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(
                    type="text", 
                    content=f"I apologize, but I encountered an issue processing your request about past visits. {fallback_content}", 
                    data=None
                )]
            )
