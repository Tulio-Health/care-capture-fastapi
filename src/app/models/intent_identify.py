from typing import Generic, List, TypeVar, Optional
from pydantic import BaseModel
from pydantic.generics import GenericModel
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions


class IntentRequest(BaseModel):
    messages: List[str]
    
T = TypeVar("T")
    
class IntentAiResponse(GenericModel , Generic[T]):
    type:str = "text"
    content:str
    data:T

class MedicalIntentAiResponse(GenericModel , Generic[T]):
    """Specialized response class for medical intents that includes citations."""
    type:str = "text"
    content:str
    citation:str  # Required citation field for medical responses
    data:T

class IntentResponse(GenericModel , Generic[T]):
    """
    Represents the response from the intent identifier.
    
    Attributes:
        intent: The identified intent
        message: The response from the appropriate handler
    """
    intent: RouterOptions
    responses: List[IntentAiResponse[T]]

class MedicalIntentResponse(GenericModel , Generic[T]):
    """
    Represents the response from medical intent handlers.
    
    Attributes:
        intent: The identified intent (should be MEDICAL_INQUIRY)
        responses: The responses with citations
    """
    intent: RouterOptions
    responses: List[MedicalIntentAiResponse[T]]