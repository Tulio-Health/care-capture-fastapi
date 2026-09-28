"""S3 client utility for downloading documents from AWS S3."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from botocore.config import Config
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
import mimetypes
import re
from typing import Tuple
import boto3
from botocore.exceptions import ClientError

from src.app.common.logging import get_logger
from src.app.core.settings import document_allowed_prefixes

logger = get_logger(__name__)
# The pool's own 4 worker threads ARE the download concurrency limit; a former companion
# semaphore with the same 4 permits could never block (only pool threads acquired it) and
# was removed (audit R2).
_DOWNLOAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="document-download")


class S3DocumentClient:
    """
    Handle S3 document downloads using AWS credentials.

    Uses the IAM instance role (AppRunner) or environment credentials (local)
    for authentication and downloads documents from S3 based on file paths
    stored in FHIR DocumentReference resources.
    """

    def __init__(self, *, allowed_prefixes=None):
        self.allowed_prefixes = allowed_prefixes
        self._s3_client = None
        self.download_versions = {}
        self.transport_decode_counts = {}

    @property
    def s3_client(self):
        if self._s3_client is None:
            self._s3_client = boto3.Session().client("s3", config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1}))
        return self._s3_client

    @s3_client.setter
    def s3_client(self, client):
        self._s3_client = client

    def parse_s3_url(self, file_path: str) -> Tuple[str, str]:
        """
        Parse S3 file path to extract bucket and key.

        Handles full S3 URIs: s3://bucket-name/path/to/file.pdf

        Args:
            file_path: Full S3 URI (e.g., s3://carecapture-dev-storage/emr/documents/file.pdf)

        Returns:
            Tuple of (bucket_name, object_key)

        Raises:
            ValueError: If file path is not a valid S3 URI

        Examples:
            >>> client.parse_s3_url("s3://my-bucket/folder/file.pdf")
            ('my-bucket', 'folder/file.pdf')
        """
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("File path cannot be empty")
        if any(ord(character) < 32 or ord(character) == 127 for character in file_path):
            raise ValueError("Invalid document storage URI")

        # Parse S3 URI: s3://bucket/key
        s3_pattern = r"^s3://([^/]+)/(.+)$"
        match = re.fullmatch(s3_pattern, file_path)

        if not match:
            raise ValueError(
                "Invalid document storage URI"
            )

        bucket = match.group(1)
        key = match.group(2)

        logger.debug("Validated document storage URI")

        return bucket, key

    def authorize_location(self, file_path):
        """Restrict document downloads to an explicit allowlist of S3 buckets.

        The production instance role is NOT scoped to these buckets (it has
        unscoped S3 access), so this allowlist is the only real access
        control on document downloads today — not defense-in-depth on top
        of IAM. A restricted caller may inject `allowed_prefixes` explicitly
        (e.g. tests, internal tooling) to further scope by key prefix within
        a bucket; otherwise the scope comes from the configured
        `document_allowed_prefixes()`, which is bucket-only — any key within
        the configured bucket is allowed. Never accept arbitrary request
        URLs here.
        """
        bucket, key = self.parse_s3_url(file_path)
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
            raise DocumentProcessingError("DOCUMENT_ACCESS_DENIED")
        entries = self.allowed_prefixes
        if entries is None:
            entries = document_allowed_prefixes()
        for entry in entries:
            if not isinstance(entry, str) or not entry.startswith("s3://"):
                continue
            allowed_bucket, _, allowed_key = entry[5:].partition("/")
            if bucket != allowed_bucket:
                continue
            if not allowed_key or key == allowed_key or (entry.endswith("/") and key.startswith(allowed_key)):
                return bucket, key
        raise DocumentProcessingError("DOCUMENT_ACCESS_DENIED")

    async def download_document(self, file_path: str) -> bytes:
        """
        Download document from S3.

        Args:
            file_path: Full S3 URI (e.g., s3://bucket/path/to/file.pdf)

        Returns:
            Document content as bytes

        Raises:
            ValueError: If file path is invalid
            ClientError: If S3 download fails (file not found, access denied, etc.)
            Exception: For other download errors
        """
        bucket, key = self.authorize_location(file_path)
        def download():
            try:
                response = self.s3_client.get_object(Bucket=bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                mapped = "DOCUMENT_NOT_FOUND" if code in {"NoSuchKey", "404"} else "DOCUMENT_ACCESS_DENIED" if code in {"AccessDenied", "403"} else "DOWNLOAD_UNAVAILABLE"
                raise DocumentProcessingError(mapped) from exc
            body = response["Body"]
            try:
                limit = DocumentTextExtractor.MAX_FILE_SIZE
                if response.get("ContentLength", 0) > limit:
                    raise DocumentProcessingError("FILE_TOO_LARGE")
                chunks, total = [], 0
                deadline = time.monotonic() + 45
                while True:
                    if time.monotonic() >= deadline:
                        raise DocumentProcessingError("DOWNLOAD_TIMEOUT")
                    chunk = body.read(min(64 * 1024, limit + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise DocumentProcessingError("FILE_TOO_LARGE")
                    chunks.append(chunk)
                content = b"".join(chunks)
                encoding = (response.get("ContentEncoding") or "identity").strip().lower()
                self.transport_decode_counts[file_path] = 0
                if encoding == "gzip":
                    import gzip
                    import io
                    try:
                        with gzip.GzipFile(fileobj=io.BytesIO(content)) as compressed:
                            content = compressed.read(limit + 1)
                    except (OSError, EOFError) as exc:
                        raise DocumentProcessingError("INVALID_COMPRESSION") from exc
                    if len(content) > limit:
                        raise DocumentProcessingError("FILE_TOO_LARGE")
                    self.transport_decode_counts[file_path] = 1
                elif encoding != "identity":
                    raise DocumentProcessingError("UNSUPPORTED_FORMAT")
                self.download_versions[file_path] = response.get("VersionId") or response.get("ETag")
                return content
            finally:
                body.close()
        return await asyncio.get_running_loop().run_in_executor(_DOWNLOAD_POOL, download)

    async def validate_download_versions(self):
        for path, version in self.download_versions.items():
            bucket, key = self.authorize_location(path)
            def head(bucket=bucket, key=key):
                return self.s3_client.head_object(Bucket=bucket, Key=key)
            current = await asyncio.get_running_loop().run_in_executor(_DOWNLOAD_POOL, head)
            if not version or (current.get("VersionId") or current.get("ETag")) != version:
                raise DocumentProcessingError("SOURCE_VERSION_CHANGED")

    def get_content_type_from_path(self, file_path: str) -> str:
        """
        Infer content type from file extension.

        Args:
            file_path: File path or name

        Returns:
            MIME content type

        Examples:
            >>> client.get_content_type_from_path("report.pdf")
            'application/pdf'
            >>> client.get_content_type_from_path("notes.docx")
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type
        logger.debug("Unknown file extension; content signature detection required")
        return "application/octet-stream"
