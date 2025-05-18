from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    """Base response model for all API responses"""
    success: bool = Field(..., description="Whether the request was successful")
    message: str = Field(..., description="Response message")
    data: Optional[T] = Field(None, description="Response data")

class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = Field(False, description="Whether the request was successful")
    error: str = Field(..., description="Error message")
    details: Optional[dict[str, Any]] = Field(None, description="Additional error details") 