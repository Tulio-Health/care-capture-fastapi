"""S3 client utility for downloading documents from AWS S3."""

import re
from typing import Tuple
import boto3
from botocore.exceptions import ClientError

from src.app.common.logging import get_logger
from src.app.core.settings import get_settings

logger = get_logger(__name__)


class S3DocumentClient:
    """
    Handle S3 document downloads using AWS credentials.

    Uses the IAM instance role (AppRunner) or environment credentials (local)
    for authentication and downloads documents from S3 based on file paths
    stored in FHIR DocumentReference resources.
    """

    def __init__(self):
        """Initialize S3 client using the ambient AWS credentials (IAM role or env vars)."""
        try:
            session = boto3.Session()
            self.s3_client = session.client("s3")
            self.settings = get_settings()

            logger.info("S3 client initialized")

        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise

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
        if not file_path:
            raise ValueError("File path cannot be empty")

        # Parse S3 URI: s3://bucket/key
        s3_pattern = r"^s3://([^/]+)/(.+)$"
        match = re.match(s3_pattern, file_path)

        if not match:
            raise ValueError(
                f"Invalid S3 URI format: {file_path}. Expected: s3://bucket/key"
            )

        bucket = match.group(1)
        key = match.group(2)

        logger.debug(f"Parsed S3 URL - bucket: {bucket}, key: {key}")

        return bucket, key

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
        try:
            # Parse S3 URL
            bucket, key = self.parse_s3_url(file_path)

            logger.info(f"Downloading document from S3 - bucket: {bucket}, key: {key}")

            # Download file from S3
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read()

            content_length = len(content)
            logger.info(
                f"Successfully downloaded document - "
                f"bucket: {bucket}, key: {key}, size: {content_length} bytes"
            )

            return content

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "NoSuchKey":
                logger.error(f"S3 file not found - bucket: {bucket}, key: {key}")
                raise ValueError(f"File not found in S3: {file_path}") from e
            elif error_code == "AccessDenied":
                logger.error(f"S3 access denied - bucket: {bucket}, key: {key}")
                raise ValueError(f"Access denied to S3 file: {file_path}") from e
            else:
                logger.error(
                    f"S3 download failed - bucket: {bucket}, key: {key}, "
                    f"error: {error_code} - {error_message}"
                )
                raise Exception(f"Failed to download from S3: {error_message}") from e

        except ValueError:
            # Re-raise ValueError (from parse_s3_url)
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error downloading from S3: {file_path}", exc_info=e
            )
            raise Exception(f"Failed to download document: {str(e)}") from e

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
        file_path_lower = file_path.lower()

        if file_path_lower.endswith(".pdf"):
            return "application/pdf"
        elif file_path_lower.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif file_path_lower.endswith(".doc"):
            return "application/msword"
        elif file_path_lower.endswith(".txt"):
            return "text/plain"
        else:
            # Default to PDF if unknown
            logger.warning(f"Unknown file extension for {file_path}, defaulting to PDF")
            return "application/pdf"
