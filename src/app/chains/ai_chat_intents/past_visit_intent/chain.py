from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser
import json
from typing import Dict, Any, List, Optional

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.models.past_visit_query import PastVisitQuery
from src.app.core import get_settings
from .constants import QUERY_PROMPT, RESPONSE_PROMPT  # Import the prompts

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

NO_PAST_VISIT_INFORMATION_AVAILABLE = "I am sorry, but I don't have any past Provider visit information available for you, please try with a different query."

class PastVisitIntentChain:
    def __init__(self):
        # Initialize output parser for final response
        self.response_parser = PydanticOutputParser(pydantic_object=IntentResponse[None])
        
        # Initialize output parser for query parameters
        self.query_parser = PydanticOutputParser(pydantic_object=PastVisitQuery)
        
        # First prompt: Extract structured query parameters
        self.query_prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_PROMPT),  # Use the imported QUERY_PROMPT
            ("user", "{text}")
        ])
        
        # Second prompt: Generate the final response based on filtered appointments
        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", RESPONSE_PROMPT),  # Use the imported RESPONSE_PROMPT
            ("user", "Here are the filtered appointments that match your criteria: {filtered_appointments}\n\nAnd here are the healthcare provider details: {providers_info}")
        ])
        
        # Chain for query extraction
        self.query_chain = self.query_prompt | model | self.query_parser
        
        # Chain for final response
        self.response_chain = self.response_prompt | model | self.response_parser

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
        if query.timeframe != 'all':
            # Implementation of date filtering based on timeframe would go here
            # This is a simplified version
            if query.timeframe == 'specific_date' and query.start_date:
                filtered = [appt for appt in filtered if appt.get('date') == query.start_date.isoformat()]
            elif query.timeframe == 'date_range' and query.start_date and query.end_date:
                filtered = [appt for appt in filtered if 
                           query.start_date.isoformat() <= appt.get('date', '') <= query.end_date.isoformat()]
        
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
    def handle_intent(self, **kwargs) -> IntentResponse[None]:
        text = kwargs['text']
        context = kwargs['context']
        
        print(f"Received context keys: {list(context.keys())}")
        
        # Extract data from context
        user_profile = context.get('user_profile', {})
        appointments = context.get('appointments', [])
        providers = context.get('healthcare_providers', [])
        visit_summary = context.get('visit_summary', '')
        chat_history = context.get('chat_history', [])
        
        print(f"User profile: {user_profile}")
        print(f"Appointments count: {len(appointments)}")
        print(f"Providers count: {len(providers)}")
        
        # If no appointment data is available
        if not appointments:
            print("No appointments found in context")
            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(type="text", content=NO_PAST_VISIT_INFORMATION_AVAILABLE, data=None)]
            )
        
        # Get sample keys from the first appointment for the schema
        appointment_keys = list(appointments[0].keys()) if appointments else []
        provider_keys = list(providers[0].keys()) if providers else []
        
        print(f"Appointment keys: {appointment_keys}")
        print(f"Provider keys: {provider_keys}")
        print(f"Extracting query parameters from: {text}")
        
        try:
            # Step 1: Extract query parameters
            query_params = self.query_chain.invoke({
                "text": text,
                "user_profile": json.dumps(user_profile, default=str),
                "appointment_keys": json.dumps(appointment_keys),
                "provider_keys": json.dumps(provider_keys),
                "healthcare_providers": json.dumps(providers, default=str),
                "query_format": self.query_parser.get_format_instructions()
            })
            
            print(f"Extracted query parameters: {query_params}")
            
            # Step 2: Filter appointments based on query
            filtered_appointments = self.filter_appointments(query_params, appointments, providers)
            
            # Get relevant provider information
            provider_ids = list(set(appt.get('provider_id') for appt in filtered_appointments if appt.get('provider_id')))
            relevant_providers = self.get_providers_info(provider_ids, providers)
            
            print(f"Found {len(filtered_appointments)} matching appointments")
            print(f"Found {len(relevant_providers)} relevant providers")
            
            # Step 3: Generate final response
            if not filtered_appointments:
                return IntentResponse[None](
                    intent="past_visits",
                    responses=[IntentAiResponse(
                        type="text", 
                        content="I'm sorry, but I couldn't find any past visits matching your criteria.", 
                        data=None
                    )]
                )
            
            # Generate the response using the filtered data
            result = self.response_chain.invoke({
                "text": text,
                "filtered_appointments": json.dumps(filtered_appointments, default=str),
                "providers_info": json.dumps(relevant_providers, default=str),
                "output_format": self.response_parser.get_format_instructions()
            })
            
            return result
            
        except Exception as e:
            print(f"Error processing past visit query: {str(e)}")
            import traceback
            traceback.print_exc()
            # Fallback to the original implementation if there's an error
            visit_summary = context.get('visit_summary', '')
            print(f"Falling back to original method. Visit summary: {visit_summary}")
            
            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(
                    type="text", 
                    content=f"I apologize, but I encountered an issue processing your request about past visits. {NO_PAST_VISIT_INFORMATION_AVAILABLE}", 
                    data=None
                )]
            )
