"""Unit tests for the `_DOWNLOAD_CAPACITY` semaphore's blocking-acquire fix.

Prior to this fix, `download_document`/`validate_download_versions` called
`_DOWNLOAD_CAPACITY.acquire(blocking=False)`, so a caller arriving while all
4 permits were transiently held (a millisecond-scale queueing event, since
`_DOWNLOAD_POOL` already caps real concurrency at 4) failed instantly and
permanently with `DOWNLOAD_BUSY` instead of simply waiting its turn.

These tests exercise `_DOWNLOAD_CAPACITY` directly -- the same module-global
semaphore object both call sites guard with -- rather than going through the
full S3 client, since the semaphore's acquire/release behavior is exactly
what changed.
"""
import asyncio
import os
import threading
import time
import unittest
from unittest.mock import MagicMock

from src.app.core.settings import reset_settings
from src.app.utils import s3_client
from src.app.utils.s3_client import S3DocumentClient


class DownloadCapacityBlockingAcquireTests(unittest.TestCase):
    def test_waiting_caller_succeeds_once_a_permit_frees_up(self):
        """5th caller blocks instead of failing instantly, then proceeds
        once one of the 4 holders releases mid-wait."""
        held = [s3_client._DOWNLOAD_CAPACITY.acquire(blocking=False) for _ in range(4)]
        self.assertTrue(all(held))

        def release_one_shortly():
            time.sleep(0.2)
            s3_client._DOWNLOAD_CAPACITY.release()

        threading.Thread(target=release_one_shortly).start()

        start = time.monotonic()
        acquired = s3_client._DOWNLOAD_CAPACITY.acquire(timeout=5)
        elapsed = time.monotonic() - start

        self.assertTrue(acquired, "waiting caller should acquire once a permit frees up")
        self.assertGreaterEqual(elapsed, 0.15, "should have actually waited, not failed instantly")

        s3_client._DOWNLOAD_CAPACITY.release()
        for _ in range(3):
            s3_client._DOWNLOAD_CAPACITY.release()

    def test_timeout_still_raises_busy_eventually_if_contention_never_clears(self):
        """If all 4 permits stay held past the timeout, the caller still
        fails with DOWNLOAD_BUSY -- the fix removes the instant failure on a
        transient blip, not the failure mode itself."""
        held = [s3_client._DOWNLOAD_CAPACITY.acquire(blocking=False) for _ in range(4)]
        self.assertTrue(all(held))
        try:
            acquired = s3_client._DOWNLOAD_CAPACITY.acquire(timeout=0.1)
            self.assertFalse(acquired, "should not acquire while all permits remain held")
        finally:
            for _ in range(4):
                s3_client._DOWNLOAD_CAPACITY.release()


class DownloadDoesNotBlockEventLoopTests(unittest.TestCase):
    """Regression test for the real bug this fix addresses: the acquire
    call must happen on the executor's worker thread, not directly in the
    coroutine body, or a contended semaphore freezes the whole event loop
    (every concurrent request the process is serving), not just this call.
    """

    def setUp(self):
        self._saved_bucket = os.environ.get("DOCUMENT_S3_BUCKET")
        os.environ["DOCUMENT_S3_BUCKET"] = "carecapture-dev-storage"
        reset_settings()

    def tearDown(self):
        if self._saved_bucket is None:
            os.environ.pop("DOCUMENT_S3_BUCKET", None)
        else:
            os.environ["DOCUMENT_S3_BUCKET"] = self._saved_bucket
        reset_settings()

    def test_event_loop_stays_responsive_while_download_waits_for_a_permit(self):
        held = [s3_client._DOWNLOAD_CAPACITY.acquire(blocking=False) for _ in range(4)]
        self.assertTrue(all(held), "expected to hold all 4 permits to force contention")

        client = S3DocumentClient()
        client.s3_client = MagicMock()

        async def scenario():
            download_task = asyncio.ensure_future(client.download_document("s3://carecapture-dev-storage/doc.pdf"))
            try:
                marker_times = []
                for _ in range(5):
                    start = time.monotonic()
                    await asyncio.sleep(0)
                    marker_times.append(time.monotonic() - start)
                    await asyncio.sleep(0.05)
                self.assertTrue(
                    all(elapsed < 1.0 for elapsed in marker_times),
                    f"event loop was blocked while download awaited a permit: {marker_times}",
                )
            finally:
                for _ in range(4):
                    s3_client._DOWNLOAD_CAPACITY.release()
                result = await download_task
                self.assertEqual(result, b"ok")

        client.s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(side_effect=[b"ok", b""]), close=MagicMock()),
            "ContentLength": 2,
        }

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
