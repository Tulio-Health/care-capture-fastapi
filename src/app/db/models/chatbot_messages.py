from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True))  # Foreign key to chatbot_conversations.id
    user_query = Column(String)
    ai_response = Column(String)
    detected_intent = Column(String)
    created_by = Column(String)
    created_at = Column(DateTime)
    updated_by = Column(String)
    updated_at = Column(DateTime)
