from typing import Dict, Callable

from src.app.chains.medical_inquiry import MedicalInquiryChain
from src.app.models.intent_identify import IntentAiResponse, IntentResponse
from .intend_identifier.models import RouterOptions
from .pastvisit_summarization import PastVisitSummarizationChain
from .health_insights_extraction import HeathInsightsExtractionChain
from .upcoming_visit import UpcomingVisitChain
from .manage_visit import ManageVisitChain

from .chat import MedicalChatChain

class IntentRouter:
    """
    A router that handles different intents and calls appropriate methods.
    
    This class:
    1. Maps intents to their corresponding handler methods
    2. Provides a unified interface to handle different types of requests
    3. Maintains instances of different chains for processing
    """
    
    def __init__(self):
        # Initialize different chains
        self.summarization_chain = PastVisitSummarizationChain()
        self.health_insights_chain = HeathInsightsExtractionChain()
        self.upcoming_visit_chain = UpcomingVisitChain()
        self.manage_visit_chain = ManageVisitChain()
        self.medical_inquiry_chain = MedicalInquiryChain()

        self.chat_chain = MedicalChatChain()
        
        # Map intents to their handler methods
        self.intent_handlers: Dict[str, Callable] = {
            RouterOptions.PAST_VISITS.value: self.handle_past_visits,
            RouterOptions.HEALTH_INSIGHTS.value: self.handle_health_insights,
            RouterOptions.UPCOMING_VISITS.value: self.handle_upcoming_visits,
            RouterOptions.MANAGE_VISITS.value: self.handle_manage_visits,
            RouterOptions.NOT_A_VALID_OPTION.value: self.handle_invalid_option,
            RouterOptions.END_CONVERSATION.value: self.handle_end_conversation,
            RouterOptions.MEDICAL_INQUIRY.value: self.handle_medical_inquiry
        }
    
    def route(self, intent: str, **kwargs) -> str:
        """
        Route the request to the appropriate handler based on intent.
        
        Args:
            intent: The identified intent
            **kwargs: Additional arguments needed by the handlers
            
        Returns:
            str: The response from the appropriate handler
        """
        handler = self.intent_handlers.get(intent, self.handle_invalid_option)
        return handler(**kwargs)
    # Priority - 2
    def handle_past_visits(self, text: str, **kwargs) -> IntentResponse:
        """Handle past visits related queries."""
        return self.past_visit_chain.summarize(text)
    
    # Priority - 1 
    def handle_health_insights(self, text: str, **kwargs) -> IntentResponse:
        """Handle health insights related queries."""
        return self.health_insights_chain.extract(text)
    
    # Priority - 3
    def handle_upcoming_visits(self, text: str, context: dict, **kwargs) -> IntentResponse:
        """Handle upcoming visits related queries."""
        return self.handle_upcoming_visits.chat(text, context)
    
    # Priority - 4
    def handle_manage_visits(self, text: str, context: dict, **kwargs) -> IntentResponse:
        """Handle visit management related queries."""
        return self.handle_manage_visits.chat(text, context)
    
    def handle_invalid_option(self, **kwargs) -> IntentResponse:
        """Handle invalid or unrecognized queries."""
        message = "Hello! I'm Tulio Care Capture Assistant. I'm here to help you with all things health-related. You can ask me about your past visits, upcoming appointments, health insights, or any other health-related questions. How can I assist you today?"
        InvalidOptionResponse = IntentResponse[None]
        return InvalidOptionResponse(intent=RouterOptions.NOT_A_VALID_OPTION.value, responses=[IntentAiResponse(type="text", content=message , data=None)])
    
    def handle_end_conversation(self, **kwargs) -> IntentResponse:
        """Handle conversation end requests."""
        message = "Thank you for using our service. Have a great day!"
        EndConversationResponse = IntentResponse[None]
        return EndConversationResponse(intent=RouterOptions.END_CONVERSATION.value, responses=[IntentAiResponse(type="text", content=message , data=None)])
    
    def handle_medical_inquiry(self, text: str, **kwargs) -> IntentResponse:
        """Handle medical inquiry related queries."""
        return self.medical_inquiry_chain.answer(text)