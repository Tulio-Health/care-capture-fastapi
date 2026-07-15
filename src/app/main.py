# src/app/main.py
import os
from fastapi import FastAPI
from contextlib import asynccontextmanager

# Configure logging first before any other imports
from .common.logging import configure_logging, get_logger
configure_logging()
logger = get_logger(__name__)

# Initialize environment and load SSM parameters BEFORE importing routes
from .config.environment import initialize_environment_sync
logger.info("Loading environment configuration before route imports...")
initialize_environment_sync()

# Now import routes after SSM parameters are loaded
from .routes import health_router, root_router, care_capture_router, ai_chat_router, users_router, schedule_visit_router, translation_router, auth_test_router, document_type_inference_router
from .routes.version import router as version_router
from .common.exception import (
    HealthCheckError,
    CareCaptureError,
    health_check_exception_handler,
    care_capture_exception_handler
)
from .common.middleware import setup_cors_middleware, setup_rate_limiter, ClerkAuthMiddleware, RequestLoggingMiddleware
from .common.exception_handlers import register_exception_handlers
from .core import get_settings
from .db.config.database import get_engine
from .db.objects.entities.users import Base
from .cache.redis import RedisClient
from .core.scheduler import init_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        # Log configuration summary for debugging
        from .config.configuration_summary import log_configuration_summary, log_redis_configuration, log_database_configuration
        log_configuration_summary()
        
        # SSM parameters already loaded synchronously during imports
        # Get settings (SSM parameters already available)
        settings = get_settings()
        
        # Run startup validation checks
        from .health.startup_checks import run_all_startup_checks
        validation_passed = await run_all_startup_checks()
        if not validation_passed:
            logger.warning("⚠️ Some startup validation checks failed, but continuing startup")
        
        # Log service configurations
        log_database_configuration()
        log_redis_configuration()
        
        # Initialize Redis client
        redis_client = RedisClient()
        app.state.redis = redis_client.client
        logger.info("Redis client initialized and attached to app state")

        # Initialize DocumentTypeRulesClient and warm up the rule cache (PIPE-04)
        from .services.document_type_rules_client import get_document_type_rules_client
        rules_client = get_document_type_rules_client()
        app.state.rules_client = rules_client
        await rules_client.warm_up()

        # Initialize scheduler
        scheduler = init_scheduler()
        app.state.scheduler = scheduler
        logger.info("Scheduler initialized and attached to app state")
        
        logger.info("🚀 FastAPI application startup complete")
        
    except Exception as e:
        logger.error(f"❌ Error during application startup: {e}")
        raise
    
    yield
    
    # Shutdown
    try:
        app.state.redis.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {e}")
    
    try:
        app.state.scheduler.shutdown()
        logger.info("Scheduler shutdown successfully")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}")


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
    
    # Add request logging middleware (should be early in the chain)
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("Request logging middleware configured")
    
    # Add Clerk authentication middleware
    app.add_middleware(ClerkAuthMiddleware)
    logger.info("Clerk authentication middleware configured")

    # Register new comprehensive exception handlers
    register_exception_handlers(app)
    
    # Register legacy exception handlers (if still needed)
    app.add_exception_handler(HealthCheckError, health_check_exception_handler)
    app.add_exception_handler(CareCaptureError, care_capture_exception_handler)
    logger.debug("All exception handlers registered")

    # Include routers
    app.include_router(root_router)
    app.include_router(health_router)
    app.include_router(version_router)
    app.include_router(care_capture_router)
    app.include_router(users_router)
    app.include_router(ai_chat_router)
    app.include_router(schedule_visit_router)
    app.include_router(translation_router)
    app.include_router(auth_test_router)
    app.include_router(document_type_inference_router)

    # Playground routes — only available in development
    if os.getenv("APP_ENV", "development") == "development":
        from src.app.routes.playground_attachment import router as playground_attachment_router
        app.include_router(playground_attachment_router)
        logger.info("Playground attachment router registered (development mode)")

    logger.debug("Routers included")

    return app

# Create the FastAPI app instance
app = get_application()


def main():
    """Main entry point for development server"""
    import uvicorn
    import os
    
    # Default port configuration
    port = int(os.getenv('PORT', 8000))
    
    logger.info(f"🚀 Starting FastAPI development server on port {port}")
    logger.info("📚 API documentation available at: http://localhost:8000/api/docs")
    
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()