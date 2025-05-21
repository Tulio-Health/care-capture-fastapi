from pydantic import BaseModel
from uuid import UUID

class AiChatRequest(BaseModel):
    message: str

    conversation_id: UUID

