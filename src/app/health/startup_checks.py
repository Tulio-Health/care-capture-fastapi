"""
Startup validation checks for FastAPI application
"""
import os
import logging
from typing import List
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def validate_clerk_key() -> bool:
    # lets validate all the clerks # Clerk Authentication
    # CLERK_PUBLIC_JWT_KEY: str = ""
    #CLERK_SECRET_KEY: str = ""
    # CLERK_PUBLISHABLE_KEY: str = ""
    
    """Validate Clerk API key at startup"""
    try: 
        clerk_key = os.getenv('CLERK_PUBLIC_JWT_KEY')
        if not clerk_key:
            logger.error("❌ Clerk API key not found in environment variables")
            return False
        
        if not clerk_key.startswith('-----BEGIN PUBLIC KEY-----'):
            logger.error("❌ Clerk API key format is invalid (should start with 'sk-')")
            return False
        
        return True
    except Exception as e:
        logger.error(f"❌ Clerk API key validation error: {e}")
        return False

async def validate_openai_key() -> bool:
    """Validate OpenAI API key at startup"""
    try:
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            logger.error("❌ OpenAI API key not found in environment variables")
            return False
            
        if not openai_key.startswith('sk-'):
            logger.error("❌ OpenAI API key format is invalid (should start with 'sk-')")
            return False
        
        # Try to import and validate with OpenAI
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            
            # Simple validation call - just list models to test authentication
            response = client.models.list()
            logger.info("✅ OpenAI API key validation successful")
            return True
        except ImportError:
            logger.warning("⚠️ OpenAI package not available for validation")
            return True  # Don't fail if package isn't available
        except Exception as openai_error:
            logger.error(f"❌ OpenAI API key validation failed: {openai_error}")
            if os.getenv('APP_ENV') == 'production':
                raise ValueError(f"Invalid OpenAI API key in production: {openai_error}")
            return False
            
    except Exception as e:
        logger.error(f"❌ OpenAI API key validation error: {e}")
        if os.getenv('APP_ENV') == 'production':
            raise ValueError(f"OpenAI API key validation failed: {e}")
        return False


async def validate_database_connection() -> bool:
    """Validate database connection at startup"""
    try:
        # Import database session
        from src.app.db.config.database import get_db
        
        # Test database connection
        async for db in get_db():
            result = await db.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database connection validation successful")
                return True
            else:
                logger.error("❌ Database connection validation failed - unexpected result")
                return False
            break  # Exit after first iteration
                
    except ImportError as e:
        logger.error(f"❌ Database module import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Database connection validation failed: {e}")
        if os.getenv('APP_ENV') == 'production':
            raise ValueError(f"Database connection failed in production: {e}")
        return False


async def validate_redis_connection() -> bool:
    """Validate Redis connection at startup"""
    try:
        import redis.asyncio as redis
        
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        redis_password = os.getenv('REDIS_PASSWORD', '')
        
        # Create Redis client
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password if redis_password else None,
            decode_responses=True
        )
        
        # Test connection
        await redis_client.ping()
        await redis_client.aclose()
        
        logger.info("✅ Redis connection validation successful")
        return True
        
    except ImportError as e:
        logger.warning(f"⚠️ Redis package not available for validation: {e}")
        return True  # Don't fail if Redis package isn't available
    except Exception as e:
        logger.error(f"❌ Redis connection validation failed: {e}")
        if os.getenv('APP_ENV') == 'production':
            logger.warning(f"Redis connection failed in production: {e}")
        return False


async def run_all_startup_checks() -> bool:
    """Run all startup validation checks"""
    logger.info("🚀 Running startup validation checks...")
    
    checks = [
        ("OpenAI API Key", validate_openai_key()),
        ("Database Connection", validate_database_connection()),
        ("Redis Connection", validate_redis_connection()),
    ]
    
    all_passed = True
    for check_name, check_coro in checks:
        try:
            result = await check_coro
            if not result:
                logger.error(f"❌ {check_name} validation failed")
                all_passed = False
            else:
                logger.info(f"✅ {check_name} validation passed")
        except Exception as e:
            logger.error(f"❌ {check_name} validation error: {e}")
            all_passed = False
    
    if all_passed:
        logger.info("🎉 All startup validation checks passed!!!")
    else:
        logger.warning("⚠️ Some startup validation checks failed")
        
    return all_passed