# src/app/main.py
from fastapi import FastAPI
import os
from .routes import health_router, root_router, care_capture_router, users_router, intend_identify_router
from contextlib import asynccontextmanager

from .routes import health_router, root_router, care_capture_router, users_router , chat_router
from .common.exception import (
    HealthCheckError,
    CareCaptureError,
    health_check_exception_handler,
    care_capture_exception_handler
)
from .common.middleware import setup_cors_middleware, setup_rate_limiter
from .common.logging import configure_logging, get_logger
from .core import get_settings
from .db.config.database import engine
from .db.objects.entities.users import Base
from .cache.redis import RedisClient

settings = get_settings()

# Configure logging
configure_logging()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_client = RedisClient()
    app.state.redis = redis_client.client
    logger.info("Redis client initialized and attached to app state")
    
    yield
    
    # Shutdown
    try:
        app.state.redis.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {e}")


def get_application() -> FastAPI:
    """Create and configure the FastAPI application"""
    logger.info("Creating FastAPI application")
    
    app = FastAPI(
        title="Care Capture AI",
        description="API for Care Capture AI - Making healthcare patient data more meaningful for patients and caregivers",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan
    )

    # Setup middleware
    setup_cors_middleware(app)
    logger.debug("CORS middleware configured")

    # Register exception handlers
    app.add_exception_handler(HealthCheckError, health_check_exception_handler)
    app.add_exception_handler(CareCaptureError, care_capture_exception_handler)
    logger.debug("Exception handlers registered")

    # Include routers
    app.include_router(root_router)
    app.include_router(health_router)
    app.include_router(care_capture_router)
    app.include_router(users_router)
    app.include_router(intend_identify_router)
    app.include_router(chat_router)
    logger.debug("Routers included")

    return app

# Create the FastAPI app instance
app = get_application()

if __name__ == "__main__":
    import uvicorn
    
    port = settings.PORT
    logger.info(f"Starting application on port {port}")
    
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )