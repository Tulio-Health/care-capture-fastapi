"""
Environment configuration and SSM parameter loading for FastAPI application
"""
import os
import logging
import asyncio
from .ssm_loader import load_ssm_configuration, load_ssm_configuration_sync, SSMParameterLoader

logger = logging.getLogger(__name__)


def initialize_environment_sync() -> None:
    """
    Synchronously initialize environment configuration WITH SSM loading
    This loads the .env file and SSM parameters before any imports
    """
    logger.info("🚀 Initializing FastAPI environment configuration (sync)...")
    
    # Load environment file if it exists
    env_file = f".env.{os.getenv('APP_ENV', 'development')}"
    if os.path.exists(env_file):
        logger.info(f"Loading environment file: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    # Load SSM parameters synchronously
    load_ssm_configuration_sync()
    
    # Log environment detection  
    is_app_runner = os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')
    ssm_loader = SSMParameterLoader()
    using_ssm = ssm_loader.should_load_ssm()
    
    if is_app_runner:
        logger.info("🏃 Running in AWS App Runner - SSM parameters loaded")
    elif using_ssm:
        logger.info("🔧 AWS credentials available - SSM parameters loaded")
    else:
        logger.info("💻 Local development mode - using environment variables")
    
    logger.info("✅ Environment initialization complete")


async def initialize_environment() -> None:
    """
    Initialize environment configuration with SSM parameter loading
    This should be called early in application startup
    """
    logger.info("🚀 Initializing FastAPI environment configuration...")
    
    # Load environment file if it exists
    env_file = f".env.{os.getenv('APP_ENV', 'development')}"
    if os.path.exists(env_file):
        logger.info(f"Loading environment file: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    # Load SSM parameters if needed
    await load_ssm_configuration()
    
    # Log environment detection
    is_app_runner = os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')
    ssm_loader = SSMParameterLoader()
    using_ssm = ssm_loader.should_load_ssm()
    
    if is_app_runner:
        logger.info("🏃 Running in AWS App Runner - SSM parameters loaded")
    elif using_ssm:
        logger.info("🔧 AWS credentials available - SSM parameters loaded")
    else:
        logger.info("💻 Local development mode - using environment variables")
    
    logger.info("✅ Environment initialization complete")


def is_aws_environment() -> bool:
    """Check if running in AWS environment"""
    return os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')


def should_use_ssm() -> bool:
    """Determine if SSM parameters should be used"""
    # Create SSM loader to test credential availability
    from .ssm_loader import SSMParameterLoader
    loader = SSMParameterLoader()
    return loader.should_load_ssm()