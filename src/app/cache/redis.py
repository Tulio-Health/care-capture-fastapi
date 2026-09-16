# app/cache/redis.py
import logging
from redis import Redis
from typing import Optional, List

from src.app.core import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    _instance = None
    _client: Optional[Redis] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Importing a route must not connect to Redis or load application secrets.
        pass

    @property
    def client(self) -> Redis:
        if self._client is None:
            settings = get_settings()
            self._client = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None, db=0, decode_responses=True,
                socket_connect_timeout=5, socket_timeout=5)
        return self._client

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def set(self, key: str, value: str, expiry: int = None) -> bool:
        return self.client.set(key, value, ex=expiry)

    def lrange(self, key: str, start: int, end: int) -> Optional[List[str]]:
        try:
            return self.client.lrange(key, start, end)
        except Exception as e:
            logger.error("Redis list read failed; error_type=%s", type(e).__name__)
            return None

redis_client = RedisClient()