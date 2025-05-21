from typing import Generic, List, TypeVar
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

class IntentResponse(GenericModel , Generic[T]):
    """
    Represents the response from the intent identifier.
    
    Attributes:
        intent: The identified intent
        message: The response from the appropriate handler
    """
    intent: RouterOptions
    responses: List[IntentAiResponse[T]]