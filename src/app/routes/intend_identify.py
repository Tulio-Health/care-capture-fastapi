from fastapi import APIRouter, HTTPException
from typing import Dict, List
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from src.app.models.intent_identify import IntentRequest, IntentResponse

from ..chains.intend_identifier import IntendIdentifierChain, RouterOptions

router = APIRouter(
    prefix="/intend-identify",
    tags=["intend-identify"]
)

@router.post("",
    response_model=IntentResponse,
    summary="Intent Identify",
    description="Endpoint to identify the intent of the user's messages",
    responses={
        200: {
            "description": "Successfully identified intent",
            "content": {
                "application/json": {
                    "example": {"intent": "general"}
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Error processing intent identification"}
                }
            }
        }
    }
)
async def intend_identify(request: IntentRequest):
    try:
        # Initialize the intent identifier
        intent_identifier = IntendIdentifierChain()
        
        # Convert messages to HumanMessage objects
        messages = [HumanMessage(content=msg) for msg in request.messages]
        
        # Get the identified intent
        intent = intent_identifier.identify_intent(messages)
        
        return {"intent": intent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 