from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class AiChatRequest(BaseModel):
    message: str  # Node.js sends "message"
    conversation_id: Optional[str] = None  # Node.js sends "conversation_id"
    user_id: Optional[str] = None  # Add user_id as optional since Node.js doesn't send it

