from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Time, Date
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, time, date

Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String)
    provider_id = Column(UUID(as_uuid=True))
    appointment_date = Column(Date)
    appointment_time = Column(Time)
    duration_minutes = Column(Integer)
    purpose = Column(String)
    location = Column(String)
    status = Column(String)
    reminder_sent = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # EHR integration field
    ehr_entity_id = Column(String, nullable=True, comment="EHR entity identifier") 