"""Unit tests for the S3 document-download bucket allowlist.

Covers `S3DocumentClient.authorize_location` and the settings-level
`document_allowed_prefixes()` fail-fast-in-production contract.

PR-5 originally scoped downloads by bucket AND a hardcoded/per-environment
key prefix. The key-prefix half was removed (dev's real EHR-sync key layout
-- `emr/documents/...` -- never matched the hardcoded `documents/` default,
which made every document access in dev fail closed). Only bucket-level
scoping remains as real access control; a key under any prefix within the
configured bucket is now allowed.
"""
import os
import unittest

from src.app.core.settings import document_allowed_prefixes, reset_settings
from src.app.services.document_extraction import DocumentProcessingError
from src.app.utils.s3_client import S3DocumentClient


class S3AuthorizeLocationTests(unittest.TestCase):
    _ENV_KEYS = ("DOCUMENT_S3_BUCKET", "APP_ENV", "DB_USER", "DB_PASSWORD")

    def setUp(self):
        self._saved_env = {key: os.environ.get(key) for key in self._ENV_KEYS}
        reset_settings()

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings()

    def _configure(self, *, bucket=None, app_env=None):
        for key, value in (
            ("DOCUMENT_S3_BUCKET", bucket),
            ("APP_ENV", app_env),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings()

    def test_configured_bucket_and_any_key_is_allowed(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        self.assertEqual(
            client.authorize_location("s3://carecapture-dev-storage/documents/report.pdf"),
            ("carecapture-dev-storage", "documents/report.pdf"),
        )

    def test_key_under_real_emr_sync_prefix_is_now_allowed(self):
        # This is the exact key shape dev's real EHR-sync writes use -- the
        # bug the removed hardcoded "documents/" prefix caused.
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        self.assertEqual(
            client.authorize_location("s3://carecapture-dev-storage/emr/documents/report.pdf"),
            ("carecapture-dev-storage", "emr/documents/report.pdf"),
        )

    def test_any_top_level_prefix_in_configured_bucket_is_allowed(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        self.assertEqual(
            client.authorize_location("s3://carecapture-dev-storage/other-stuff/report.pdf"),
            ("carecapture-dev-storage", "other-stuff/report.pdf"),
        )
        self.assertEqual(
            client.authorize_location("s3://carecapture-dev-storage/documents-other/x.pdf"),
            ("carecapture-dev-storage", "documents-other/x.pdf"),
        )

    def test_different_bucket_is_denied(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        with self.assertRaises(DocumentProcessingError) as failure:
            client.authorize_location("s3://some-other-bucket/documents/report.pdf")
        self.assertEqual(failure.exception.code, "DOCUMENT_ACCESS_DENIED")

    def test_document_allowed_prefixes_fails_loud_in_production_and_denies_in_dev(self):
        # DB_USER/DB_PASSWORD are required for Settings() to even construct in
        # production (a pre-existing, unrelated validator) -- set them so this
        # test isolates the DOCUMENT_S3_BUCKET fail-fast behavior specifically.
        os.environ["DB_USER"] = "synthetic"
        os.environ["DB_PASSWORD"] = "synthetic"
        self._configure(bucket=None, app_env="production")
        with self.assertRaises(RuntimeError):
            document_allowed_prefixes()

        self._configure(bucket=None, app_env="development")
        self.assertEqual(document_allowed_prefixes(), [])

    def test_configured_allowlist_is_bucket_only_no_key_prefix(self):
        self._configure(bucket="carecapture-dev-storage")
        self.assertEqual(document_allowed_prefixes(), ["s3://carecapture-dev-storage"])

    def test_explicit_prefix_injection_still_scopes_by_key_prefix(self):
        # Explicit injection (tests, internal tooling) can still narrow to a
        # sub-path -- only the *configured default* scope is bucket-only now.
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient(allowed_prefixes=["s3://other-bucket/special/"])
        self.assertEqual(
            client.authorize_location("s3://other-bucket/special/file.pdf"),
            ("other-bucket", "special/file.pdf"),
        )
        with self.assertRaises(DocumentProcessingError) as failure:
            client.authorize_location("s3://other-bucket/special-other/file.pdf")
        self.assertEqual(failure.exception.code, "DOCUMENT_ACCESS_DENIED")


if __name__ == "__main__":
    unittest.main()
