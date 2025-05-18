from typing import Generic, TypeVar, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.config.database import get_db
from ..common.logging import get_logger

T = TypeVar('T')

class BaseService(Generic[T]):
    """Base service class with common functionality"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    async def get_db(self) -> AsyncSession:
        """Get database session"""
        async for session in get_db():
            return session
    
    async def handle_error(self, error: Exception, context: Optional[dict[str, Any]] = None) -> None:
        """Handle service errors with proper logging"""
        self.logger.error(
            f"Error in {self.__class__.__name__}: {str(error)}",
            extra={"context": context} if context else None
        )
        raise error 