"""
Configuration summary logging for debugging
"""
import os
import logging

logger = logging.getLogger(__name__)


def log_configuration_summary():
    """Log configuration summary for debugging"""
    logger.info("🔧 Configuration Summary:")
    logger.info(f"  APP_ENV: {os.getenv('APP_ENV', 'NOT_SET')}")
    logger.info(f"  SSM_PARAMETER_PREFIX: {os.getenv('SSM_PARAMETER_PREFIX', 'NOT_SET')}")
    logger.info(f"  DB_HOST: {os.getenv('DB_HOST', 'NOT_SET')}")
    logger.info(f"  DB_PORT: {os.getenv('DB_PORT', 'NOT_SET')}")
    logger.info(f"  DB_NAME: {os.getenv('DB_NAME', 'NOT_SET')}")
    logger.info(f"  REDIS_HOST: {os.getenv('REDIS_HOST', 'NOT_SET')}")
    logger.info(f"  REDIS_PORT: {os.getenv('REDIS_PORT', 'NOT_SET')}")
    logger.info(f"  OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT_SET'}")
    logger.info(f"  AWS_REGION: {os.getenv('AWS_REGION', 'NOT_SET')}")
    logger.info(f"  AWS_EXECUTION_ENV: {os.getenv('AWS_EXECUTION_ENV', 'NOT_SET')}")


def log_redis_configuration():
    """Log Redis service details"""
    redis_host = os.getenv('REDIS_HOST', 'NOT_SET')
    redis_port = os.getenv('REDIS_PORT', 'NOT_SET')
    logger.info(f"📡 Redis Service Configuration: {redis_host}:{redis_port}")


def log_database_configuration():
    """Log Database service details"""
    db_host = os.getenv('DB_HOST', 'NOT_SET')
    db_port = os.getenv('DB_PORT', 'NOT_SET')
    db_name = os.getenv('DB_NAME', 'NOT_SET')
    logger.info(f"🗄️ Database Configuration: {db_host}:{db_port}/{db_name}")