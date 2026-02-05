from sqlalchemy import Column, String, JSON, Text , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, func
from pydantic import ConfigDict

Base = declarative_base()

class ConversationSummaries(Base):
    __tablename__ = "conversation_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    appointment_id = Column(UUID(as_uuid=True), nullable=False , unique=True , index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    summary_text = Column(Text, nullable=False)
    key_points = Column(JSON, nullable=True)
    medications = Column(JSON, nullable=True)
    diagnoses = Column(JSON, nullable=True)
    instructions = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    summary_metadata = Column("metadata", JSON, nullable=True)
    
    # Audit columns
    created_at = Column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', NOW())"))  
    updated_at = Column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', NOW())"), onupdate=text("TIMEZONE('utc', NOW())"))
    created_by = Column(UUID(as_uuid=True), nullable=False)
    updated_by = Column(UUID(as_uuid=True), nullable=False)

    model_config = ConfigDict(
        from_attributes=True, 
        populate_by_name=True,
        json_encoders={
            UUID: str
        }
    )

    def __repr__(self):
        return f"<ConversationSummaries(id={self.id}, appointment_id={self.appointment_id})>"