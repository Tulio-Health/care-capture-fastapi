from pydantic import BaseModel
from uuid import UUID

class AiChatRequest(BaseModel):
    message: str
    user_id: UUID
    conversation_id: UUID

