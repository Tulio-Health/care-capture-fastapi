from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from datetime import date, datetime, timedelta

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.models.upcoming_visit_query import UpcomingVisitQuery
from src.app.models.conversation_summaries import ConversationSummary as PydanticConversationSummary
from src.app.db.objects.entities.conversation_summaries import ConversationSummaries as ORMConversationSummaries
from src.app.chains.ai_chat_intents.not_found_intent.chain import NoDataFoundIntentChain
from .constants import QUERY_PROMPT, RESPONSE_PROMPT

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer


NO_UPCOMING_VISIT_INFORMATION_AVAILABLE = "I am sorry, but I don't have any Upcoming Provider visit information available for you, please try with a different query."

class UpcomingVisitIntentChain:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Initialize the no data found chain
        self.no_data_found_chain = NoDataFoundIntentChain()
        self._model = None
        
        # Initialize output parser for query parameters
        self.query_parser = PydanticOutputParser(pydantic_object=UpcomingVisitQuery)
        
        # First prompt: Extract structured query parameters
        self.query_prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_PROMPT),
            ("user", "Generate the query parameters for the following user question: {text}")
        ])
        # Today's date in ISO format
        today_date = date.today().isoformat()
        # Second prompt: Generate the final response based on filtered appointments
        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", RESPONSE_PROMPT),
            ("user", "User Original Question: {text}\nConversation History: {conversation_history}\nFiltered Appointments: {filtered_appointments}\nHealthcare Provider Details: {providers_info}\nToday's Date: {today_date}")
        ])
        
        # Lazy load chains
        self._query_chain = None
        self._response_content_chain = None

    def filter_appointments(self, query: UpcomingVisitQuery, appointments: List[Dict[str, Any]], providers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter appointments based on the query parameters
        """
        # Start with all appointments
        filtered = appointments
        
        # Apply filters based on query parameters
        if query.npi:
            # First find the provider name from the appointments data
            provider_name = None
            for appt in appointments:
                if appt.get('npi') == query.npi:
                    first_name = appt.get('provider_first_name', '')
                    last_name = appt.get('provider_last_name', '')
                    if first_name and last_name:
                        provider_name = f"{first_name} {last_name}"
                        break
            
            # If we found the provider name, filter by name to catch all appointments for this provider
            if provider_name:
                filtered = [appt for appt in filtered if 
                          f"{appt.get('provider_first_name', '')} {appt.get('provider_last_name', '')}" == provider_name]
            else:
                # Fallback to npi filtering if no name found
                filtered = [appt for appt in filtered if appt.get('npi') == query.npi]
        
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
        today_iso = today.isoformat()  # Use today's date instead of yesterday
        
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
            # Default case (including when timeframe is 'all'): include appointments from today onwards
            filtered = [appt for appt in filtered if appt.get('date', '') >= today_iso]
        
        # Sort the results
        if query.sort_by == 'date':
            filtered.sort(key=lambda x: x.get('date', ''), reverse=(query.sort_order == 'desc'))
        elif query.sort_by == 'provider':
            filtered.sort(key=lambda x: x.get('provider_id', ''), reverse=(query.sort_order == 'desc'))
        
        # Apply limit if specified
        if query.limit and len(filtered) > query.limit:
            filtered = filtered[:query.limit]
        
        # If more than 5 appointments after filtering, keep only the 5 closest to today
        if len(filtered) > 5:
            today = date.today()
            # Sort by absolute difference from today's date to get closest appointments
            filtered.sort(key=lambda x: abs((datetime.strptime(x.get('date', ''), '%Y-%m-%d').date() - today).days))
            filtered = filtered[:5]
            
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
            return await self.no_data_found_chain.handle_intent(
                text=text,
                context=context,
                intent="upcoming_visits",
                search_details="upcoming appointments"
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
            }, config={"callbacks": [get_tracer()]})

            print(f"Extracted queryy parameters: {query_params}")

            # Step 2: Filter appointments based on query
            print(f"All appointments: {appointments}")
            filtered_appointments = self.filter_appointments(query_params, appointments, [])
            print(f"Found {len(filtered_appointments)} relevant appointments")

            # Step 3: Generate final response
            if not filtered_appointments:
                # Create search details based on query parameters
                search_details = self._create_search_details(query_params)
                return await self.no_data_found_chain.handle_intent(
                    text=text,
                    context=context,
                    intent="upcoming_visits",
                    search_details=search_details
                )
            
            # Today's date in ISO format
            today_date = date.today().isoformat()

            ai_content_string = await self.response_content_chain.ainvoke({
                "text": text,
                "today_date": today_date,
                "conversation_history": json.dumps(chat_history, default=str),
                "filtered_appointments": json.dumps(filtered_appointments, default=str),
                "providers_info": json.dumps([], default=str),
            }, config={"callbacks": [get_tracer()]})

            return IntentResponse[None](
                intent="upcoming_visits",
                responses=[IntentAiResponse(type="text", content=ai_content_string, data=None)]
            )

        except Exception as e:
            print(f"Error processing upcoming visit query: {str(e)}")
            import traceback
            traceback.print_exc()
            fallback_content = NO_UPCOMING_VISIT_INFORMATION_AVAILABLE
            print(f"Falling back. Content: {fallback_content}")
            return IntentResponse[None](
                intent="upcoming_visits",
                responses=[IntentAiResponse(
                    type="text", 
                    content=f"I apologize, but I encountered an issue processing your request about upcoming visits. {fallback_content}", 
                    data=None
                )]
            )

    def _create_search_details(self, query_params: UpcomingVisitQuery) -> str:
        """Create a human-readable description of what was searched for"""
        details = []
        if query_params.provider_name:
            details.append(f"appointments with {query_params.provider_name}")
        if query_params.purpose:
            details.append(f"appointments for {query_params.purpose}")
        if query_params.location:
            details.append(f"appointments at {query_params.location}")
        if query_params.start_date:
            if query_params.timeframe == 'specific_date':
                details.append(f"appointments on {query_params.start_date}")
            elif query_params.end_date:
                details.append(f"appointments between {query_params.start_date} and {query_params.end_date}")
            else:
                details.append(f"appointments from {query_params.start_date}")
        
    @property
    def model(self):
        """Lazy load the model on first access"""
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model
    
    @property
    def query_chain(self):
        """Lazy load the query chain on first access"""
        if self._query_chain is None:
            self._query_chain = self.query_prompt | self.model | self.query_parser
        return self._query_chain
    
    @property
    def response_content_chain(self):
        """Lazy load the response content chain on first access"""
        if self._response_content_chain is None:
            self._response_content_chain = self.response_prompt | self.model | StrOutputParser()
        return self._response_content_chain

        return " ".join(details) if details else "upcoming appointments matching your criteria"
