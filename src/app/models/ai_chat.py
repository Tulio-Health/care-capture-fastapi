from pydantic import BaseModel

class AiChatRequest(BaseModel):
    message: str
    conversation_id: str
    user_id: str
