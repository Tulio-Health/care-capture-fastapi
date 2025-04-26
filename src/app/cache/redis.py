# app/cache/redis.py
import logging
from redis import Redis
from typing import Optional

from src.app.core import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class RedisClient:
    _instance = None
    _client: Optional[Redis] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            try:
                self._client = Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True
                )
                self._client.ping()
                logger.info("Redis client initialized")
            except ConnectionError as e:
                logger.info(f"Redis connection error: {e}")
                raise
            except Exception as e:
                logger.info(f"Redis error: {e}")
                raise

    @property
    def client(self) -> Redis:
        return self._client

    def get(self, key: str) -> Optional[str]:
        return self._client.get(key)

    def set(self, key: str, value: str, expiry: int = None) -> bool:
        return self._client.set(key, value, ex=expiry)

redis_client = RedisClient()