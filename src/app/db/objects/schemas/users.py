from pydantic import BaseModel, EmailStr
from datetime import datetime
from uuid import UUID
from typing import Optional

class UsersBase(BaseModel):
    """Base schema for Users."""
    email: EmailStr
    clerk_id: str
    status: str = "ACTIVE"

class UsersCreate(UsersBase):
    """Schema for creating a new Users."""
    pass

class UsersUpdate(BaseModel):
    """Schema for updating a Users."""
    email: Optional[EmailStr] = None
    status: Optional[str] = None

class UsersInDB(UsersBase):
    """Schema for Users as stored in database."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 