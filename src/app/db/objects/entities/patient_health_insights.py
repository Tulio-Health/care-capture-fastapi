from sqlalchemy import Column, String, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, func

Base = declarative_base()

class PatientHealthInsights(Base):
    __tablename__ = "patient_health_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    health_insights = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<PatientHealthInsights(id={self.id}, user_id={self.user_id})>"