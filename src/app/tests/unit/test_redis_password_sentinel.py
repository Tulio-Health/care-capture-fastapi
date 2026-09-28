"""Unit tests for the Redis "NONE" sentinel-password handling.

AWS SSM stores the unset-password parameter as the literal string "NONE"
(case-insensitive) rather than an empty value. `resolve_redis_password`
normalizes that (and an empty string) to `None`; both `RedisClient.client`
(src/app/cache/redis.py) and `validate_redis_connection`
(src/app/health/startup_checks.py) must route through it instead of a naive
`value or None` / `value if value else None` truthy check, which lets the
literal string "NONE" through as a real password.
"""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.app.core.settings import reset_settings, resolve_redis_password


class ResolveRedisPasswordTests(unittest.TestCase):
    def test_none_sentinel_case_variants_resolve_to_none(self):
        for raw in ("NONE", "none", "None", "nOnE"):
            with self.subTest(raw=raw):
                self.assertIsNone(resolve_redis_password(raw))

    def test_empty_string_resolves_to_none(self):
        self.assertIsNone(resolve_redis_password(""))

    def test_real_password_passes_through_unchanged(self):
        self.assertEqual(resolve_redis_password("a-real-password"), "a-real-password")


class RedisClientPasswordSentinelTests(unittest.TestCase):
    """Covers RedisClient.client (src/app/cache/redis.py)."""

    def setUp(self):
        self._saved_password = os.environ.get("REDIS_PASSWORD")
        import src.app.cache.redis as redis_module
        self.redis_module = redis_module
        redis_module.RedisClient._instance = None
        redis_module.RedisClient._client = None
        reset_settings()

    def tearDown(self):
        if self._saved_password is None:
            os.environ.pop("REDIS_PASSWORD", None)
        else:
            os.environ["REDIS_PASSWORD"] = self._saved_password
        self.redis_module.RedisClient._instance = None
        self.redis_module.RedisClient._client = None
        reset_settings()

    def _password_passed_to_redis(self, redis_password_env):
        os.environ["REDIS_PASSWORD"] = redis_password_env
        reset_settings()
        with patch.object(self.redis_module, "Redis") as mock_redis_cls:
            mock_redis_cls.return_value = MagicMock()
            client = self.redis_module.RedisClient()
            client.client  # trigger lazy construction
            _, kwargs = mock_redis_cls.call_args
            return kwargs["password"]

    def test_none_sentinel_is_not_passed_to_redis_client(self):
        self.assertIsNone(self._password_passed_to_redis("NONE"))

    def test_lowercase_none_sentinel_is_not_passed_to_redis_client(self):
        self.assertIsNone(self._password_passed_to_redis("none"))

    def test_empty_password_is_not_passed_to_redis_client(self):
        self.assertIsNone(self._password_passed_to_redis(""))

    def test_real_password_is_passed_to_redis_client_unchanged(self):
        self.assertEqual(self._password_passed_to_redis("a-real-password"), "a-real-password")


class ValidateRedisConnectionSentinelTests(unittest.IsolatedAsyncioTestCase):
    """Covers validate_redis_connection (src/app/health/startup_checks.py) --
    this is the function directly causing dev's live 503 (app.state.summary_ready
    is set False when it fails)."""

    async def _run_with_password(self, redis_password_env):
        saved = os.environ.get("REDIS_PASSWORD")
        os.environ["REDIS_PASSWORD"] = redis_password_env
        try:
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_instance = MagicMock()
                mock_instance.ping = AsyncMock()
                mock_instance.aclose = AsyncMock()
                mock_redis_cls.return_value = mock_instance
                from src.app.health.startup_checks import validate_redis_connection
                result = await validate_redis_connection()
                _, kwargs = mock_redis_cls.call_args
                return result, kwargs["password"]
        finally:
            if saved is None:
                os.environ.pop("REDIS_PASSWORD", None)
            else:
                os.environ["REDIS_PASSWORD"] = saved

    async def test_none_sentinel_does_not_fail_startup_validation(self):
        result, password = await self._run_with_password("NONE")
        self.assertTrue(result)
        self.assertIsNone(password)

    async def test_real_password_still_passed_through_at_startup(self):
        result, password = await self._run_with_password("a-real-password")
        self.assertTrue(result)
        self.assertEqual(password, "a-real-password")


if __name__ == "__main__":
    unittest.main()
