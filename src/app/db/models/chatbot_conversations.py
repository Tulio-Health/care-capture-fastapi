from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

class ChatbotConversation(Base):
    __tablename__ = "chatbot_conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String)
    start_timestamp = Column(DateTime)
    end_timestamp = Column(DateTime)
    context = Column(String)
    created_by = Column(String)
    created_at = Column(DateTime)
    updated_by = Column(String)
    updated_at = Column(DateTime) 