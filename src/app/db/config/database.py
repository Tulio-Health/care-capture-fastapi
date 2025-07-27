from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from typing import AsyncGenerator
from ...core.settings import get_settings
import os

settings = get_settings()

# AWS App Runner specific configuration
is_app_runner = os.getenv("AWS_EXECUTION_ENV", "").startswith("AWS_App_Runner")

# Create async engine with appropriate configuration for App Runner
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
        "pool_timeout": 120,  # Increased from 30 to 120 seconds for App Runner
        "connect_args": {
            "server_settings": {
                "application_name": "care-capture-fastapi"
            },
            "command_timeout": 120,  # Increased from 60 to 120 seconds
            "timeout": 120  # Increased from 30 to 120 seconds
        }
    })
else:
    # Keep NullPool for local development
    engine_config["poolclass"] = NullPool

engine = create_async_engine(
    str(settings.DATABASE_URL),
    **engine_config
)

# Create async session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close() 