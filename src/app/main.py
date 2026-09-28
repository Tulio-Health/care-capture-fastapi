"""Production ASGI entrypoint. Use application.get_application for isolated QA."""
from .common.logging import configure_logging, get_logger
from .application import get_application

configure_logging()
logger = get_logger(__name__)
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
