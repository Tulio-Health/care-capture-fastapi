from sqlalchemy import Column, Integer, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime, func

Base = declarative_base()

class PatientHealthInsights(Base):
    __tablename__ = "patient_health_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    insight_data = Column(JSON, nullable=False)
    is_viewed = Column(Boolean, default=False)
    additional_metadata = Column(JSON, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PatientHealthInsights(id={self.id}, user_id={self.user_id})>"