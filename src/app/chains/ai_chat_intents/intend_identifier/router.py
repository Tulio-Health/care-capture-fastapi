from typing import Dict, Callable
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.chains.ai_chat_intents.medical_inquiry_intent.chain import MedicalInquiryIntentChain
from src.app.chains.ai_chat_intents.health_insights_intent.chain import HealthInsightsIntentChain
from src.app.chains.ai_chat_intents.past_visit_intent.chain import PastVisitIntentChain
from src.app.chains.ai_chat_intents.upcoming_visit_intent.chain import UpcomingVisitIntentChain
from src.app.chains.ai_chat_intents.not_valid_intent.chain import NotValidIntentChain
from src.app.models.intent_identify import IntentAiResponse, IntentResponse

class IntentRouter:
    """
    A router that handles different intents and calls appropriate methods.
    
    This class:
    1. Maps intents to their corresponding handler methods
    2. Provides a unified interface to handle different types of requests
    3. Maintains instances of different chains for processing
    """
    
    def __init__(self, db: AsyncSession):
        # Store the database session
        self.db = db
        
        # Initialize different chains
        # TODO: PastVisitSummarizationChain is still in development
        self.past_visit_chain = PastVisitIntentChain(db=self.db) # Pass db session

        # TODO: PastVisitSummarizationChain is still in development, working... need some refinement to the response object...
        self.health_insights_chain = HealthInsightsIntentChain() # MVP - Pulls the details from the health insights table
        self.upcoming_visit_chain = UpcomingVisitIntentChain(db=self.db) # PostMVP - Pulls the details from the appointment visit table
        # self.manage_visit_chain = ManageVisitChain() # PostMVP - Pulls the details from the manage visit table
        self.medical_inquiry_chain = MedicalInquiryIntentChain() # MVP - Any generic medical inquiry
        self.not_valid_intent_chain = NotValidIntentChain() # Handle invalid options with LLM guidance

        # self.chat_chain = MedicalChatChain() # This might not be needed , will review later 
        
        # Map intents to their handler methods
        self.intent_handlers: Dict[str, Callable] = {
            RouterOptions.PAST_VISITS.value: self.handle_past_visits,
            RouterOptions.HEALTH_INSIGHTS.value: self.handle_health_insights,
            RouterOptions.UPCOMING_VISITS.value: self.handle_upcoming_visits,
            # RouterOptions.MANAGE_VISITS.value: self.handle_manage_visits,
            RouterOptions.NOT_A_VALID_OPTION.value: self.handle_invalid_option,
            RouterOptions.END_CONVERSATION.value: self.handle_end_conversation,
            RouterOptions.MEDICAL_INQUIRY.value: self.handle_medical_inquiry
        }
    
    async def route(self, intent: str, **kwargs) -> str:
        """
        Route the request to the appropriate handler based on intent.
        
        Args:
            intent: The identified intent
            **kwargs: Additional arguments needed by the handlers
            
        Returns:
            str: The response from the appropriate handler
        """
        print(f"DEBUG: Routing intent: {intent}")
        handler = self.intent_handlers.get(intent, self.handle_invalid_option)
        return await handler(**kwargs)
    
    # Priority - 2
    async def handle_past_visits(self, **kwargs) -> IntentResponse:
        """Handle past visits related queries."""
        return await self.past_visit_chain.handle_intent(**kwargs)
    
    # Priority - 1
    async def handle_health_insights(self, **kwargs) -> IntentResponse:
        """Handle health insights related queries."""
        return await self.health_insights_chain.handle_intent(**kwargs)
    
    # # Priority - 3
    async def handle_upcoming_visits(self, **kwargs) -> IntentResponse:
        """Handle upcoming visits related queries."""
        return await self.upcoming_visit_chain.handle_intent(**kwargs)
    
    # # Priority - 4
    # async def handle_manage_visits(self, text: str, context: dict, **kwargs) -> IntentResponse:
    #     """Handle visit management related queries."""
    #     return self.handle_manage_visits.chat(text, context)
    
    async def handle_invalid_option(self, **kwargs) -> IntentResponse:
        """Handle invalid or unrecognized queries."""
        return await self.not_valid_intent_chain.handle_intent(**kwargs)
    
    async def handle_end_conversation(self, **kwargs) -> IntentResponse:
        """Handle conversation end requests."""
        message = "Thank you for using our service. Have a great day!"
        EndConversationResponse = IntentResponse[None]
        return EndConversationResponse(intent=RouterOptions.END_CONVERSATION.value, responses=[IntentAiResponse(type="text", content=message , data=None)])
    
    async def handle_medical_inquiry(self, **kwargs) -> IntentResponse:
        """Handle medical inquiry related queries."""
        # return await self.medical_inquiry_chain.handle_intent(**kwargs) 
        return await self.not_valid_intent_chain.handle_intent(**kwargs) # TEMPORAL FIX. NEED TO ADD CITATIONS AND REFERENCES FOR APPSTORE.
    