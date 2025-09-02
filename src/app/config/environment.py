"""
Environment configuration and SSM parameter loading for FastAPI application
"""
import os
import logging
import asyncio
from .ssm_loader import load_ssm_configuration

logger = logging.getLogger(__name__)


def initialize_environment_sync() -> None:
    """
    Synchronously initialize environment configuration WITHOUT SSM loading
    SSM will be loaded in the async lifespan function
    This just loads the .env file
    """
    logger.info("🚀 Initializing FastAPI environment configuration (sync)...")
    
    # Load environment file if it exists
    env_file = f".env.{os.getenv('NODE_ENV', 'development')}"
    if os.path.exists(env_file):
        logger.info(f"Loading environment file: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    # Log environment detection  
    is_app_runner = os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')
    use_ssm_locally = os.getenv('USE_SSM_LOCALLY', 'false').lower() == 'true'
    
    if is_app_runner:
        logger.info("🏃 Running in AWS App Runner - SSM parameters will be loaded")
    elif use_ssm_locally:
        logger.info("🔧 Local development with SSM parameters enabled - will load SSM")
    else:
        logger.info("💻 Local development mode - using environment variables")
    
    logger.info("✅ Environment file initialization complete")


async def initialize_environment() -> None:
    """
    Initialize environment configuration with SSM parameter loading
    This should be called early in application startup
    """
    logger.info("🚀 Initializing FastAPI environment configuration...")
    
    # Load environment file if it exists
    env_file = f".env.{os.getenv('NODE_ENV', 'development')}"
    if os.path.exists(env_file):
        logger.info(f"Loading environment file: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    # Load SSM parameters if needed
    await load_ssm_configuration()
    
    # Log environment detection
    is_app_runner = os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')
    use_ssm_locally = os.getenv('USE_SSM_LOCALLY', 'false').lower() == 'true'
    
    if is_app_runner:
        logger.info("🏃 Running in AWS App Runner - SSM parameters loaded")
    elif use_ssm_locally:
        logger.info("🔧 Local development with SSM parameters enabled")
    else:
        logger.info("💻 Local development mode - using environment variables")
    
    logger.info("✅ Environment initialization complete")


def is_aws_environment() -> bool:
    """Check if running in AWS environment"""
    return os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')


def should_use_ssm() -> bool:
    """Determine if SSM parameters should be used"""
    return is_aws_environment() or os.getenv('USE_SSM_LOCALLY', 'false').lower() == 'true'