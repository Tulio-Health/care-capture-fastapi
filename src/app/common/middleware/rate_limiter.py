from fastapi import FastAPI
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
import os
from typing import Optional

# Environment variables
REDIS_URL = "REDIS_URL"
RATE_LIMIT_PER_MINUTE = "RATE_LIMIT_PER_MINUTE"

# Default values
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_RATE_LIMIT = 60  # requests per minute

async def setup_rate_limiter(
    app: FastAPI,
    redis_url: Optional[str] = None,
    rate_limit: Optional[int] = None
) -> None:
    """
    Configure rate limiting for the FastAPI application
    
    Args:
        app: FastAPI application instance
        redis_url: Redis connection URL
        rate_limit: Number of requests allowed per minute
    """
    redis_url = redis_url or os.getenv(REDIS_URL, DEFAULT_REDIS_URL)
    rate_limit = rate_limit or int(os.getenv(RATE_LIMIT_PER_MINUTE, DEFAULT_RATE_LIMIT))
    
    # Initialize Redis connection
    redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    
    # Initialize rate limiter
    await FastAPILimiter.init(redis_client)
    
    # Add rate limiter dependency to the app
    app.state.rate_limiter = RateLimiter(times=rate_limit, minutes=1) 