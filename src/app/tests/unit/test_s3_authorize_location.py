"""Unit tests for the S3 document-download allowlist.

Covers `S3DocumentClient.authorize_location` and the settings-level
`document_allowed_prefixes()` fail-fast-in-production contract (PR-5:
restores the allowlist that a follow-up commit accidentally deleted,
turning a deny-all bug into an allow-all one).
"""
import os
import unittest

from src.app.core.settings import document_allowed_prefixes, reset_settings
from src.app.services.document_extraction import DocumentProcessingError
from src.app.utils.s3_client import S3DocumentClient


class S3AuthorizeLocationTests(unittest.TestCase):
    _ENV_KEYS = ("DOCUMENT_S3_BUCKET", "DOCUMENT_S3_KEY_PREFIX", "APP_ENV", "DB_USER", "DB_PASSWORD")

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

    def _configure(self, *, bucket=None, prefix=None, app_env=None):
        for key, value in (
            ("DOCUMENT_S3_BUCKET", bucket),
            ("DOCUMENT_S3_KEY_PREFIX", prefix),
            ("APP_ENV", app_env),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings()

    def test_configured_bucket_and_matching_key_is_allowed(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        self.assertEqual(
            client.authorize_location("s3://carecapture-dev-storage/documents/report.pdf"),
            ("carecapture-dev-storage", "documents/report.pdf"),
        )

    def test_same_bucket_different_top_level_prefix_is_denied(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        with self.assertRaises(DocumentProcessingError) as failure:
            client.authorize_location("s3://carecapture-dev-storage/other-stuff/report.pdf")
        self.assertEqual(failure.exception.code, "DOCUMENT_ACCESS_DENIED")

    def test_different_bucket_is_denied(self):
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        with self.assertRaises(DocumentProcessingError) as failure:
            client.authorize_location("s3://some-other-bucket/documents/report.pdf")
        self.assertEqual(failure.exception.code, "DOCUMENT_ACCESS_DENIED")

    def test_prefix_that_merely_starts_with_documents_is_denied(self):
        # Guards against a missing trailing slash silently widening the allowed
        # scope (e.g. "documents" matching "documents-other/...").
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient()
        with self.assertRaises(DocumentProcessingError) as failure:
            client.authorize_location("s3://carecapture-dev-storage/documents-other/x.pdf")
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

    def test_explicit_prefix_injection_overrides_configured_default(self):
        # Configured default scope would deny this key entirely (different
        # bucket) -- an explicitly injected allowlist wins over it.
        self._configure(bucket="carecapture-dev-storage")
        client = S3DocumentClient(allowed_prefixes=["s3://other-bucket/special/"])
        self.assertEqual(
            client.authorize_location("s3://other-bucket/special/file.pdf"),
            ("other-bucket", "special/file.pdf"),
        )


if __name__ == "__main__":
    unittest.main()
