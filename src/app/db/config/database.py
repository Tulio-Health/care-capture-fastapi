from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from typing import AsyncGenerator, Optional
from ...core.settings import get_settings
import os
import logging

logger = logging.getLogger(__name__)

# Global variables for lazy initialization
_engine: Optional[AsyncEngine] = None
_async_session_factory = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine with SSM-loaded settings"""
    global _engine
    
    if _engine is None:
        # Get settings when engine is actually needed (after SSM loading)
        settings = get_settings()
        
        # AWS App Runner specific configuration
        is_app_runner = os.getenv("AWS_EXECUTION_ENV", "").startswith("AWS_App_Runner")
        
        # Create async engine with appropriate configuration
        engine_config = {
            "echo": settings.DEBUG,
            "pool_pre_ping": True,  # Test connections before using them
            "pool_recycle": 300,    # Recycle connections after 5 minutes
        }
        
        if is_app_runner:
            # Use AsyncAdaptedQueuePool for better connection management in App Runner
            engine_config.update({
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 120,
                "connect_args": {
                    "server_settings": {
                        "application_name": "care-capture-fastapi"
                    },
                    "command_timeout": 120,
                    "timeout": 120
                }
            })
        else:
            # Keep NullPool for local development
            engine_config["poolclass"] = NullPool
        
        database_url = str(settings.DATABASE_URL)
        logger.info(f"Creating database engine for: {database_url.split('@')[1] if '@' in database_url else database_url}")
        
        _engine = create_async_engine(
            database_url,
            **engine_config
        )
    
    return _engine


def get_session_factory():
    """Get or create the async session factory"""
    global _async_session_factory
    
    if _async_session_factory is None:
        _async_session_factory = sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    return _async_session_factory


# For backward compatibility
@property
def engine() -> AsyncEngine:
    """Property for backward compatibility"""
    return get_engine()


# For backward compatibility - will be created on first use
async_session_factory = None

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close() 