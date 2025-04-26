from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from uuid import uuid4

Base = declarative_base()

class Users(Base):
    """User profile entity representing a user in the system."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, server_default="uuid_generate_v4()")
    clerk_id = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Users(id={self.id}, email={self.email}, status={self.status})>" 