from pydantic import BaseModel, ConfigDict, Field, model_validator

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
