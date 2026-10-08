"""Unit tests for `.reason_code` persistence on `process_attachments`'s per-document path.

round9-revision3.md Sec 3.2 step 1 (Fix 2): `document.extraction_error` already carried the
public, canonical `.code` (e.g. EXTRACTION_QUALITY_FAILED), but the more specific
`.reason_code` (e.g. INVALID_TEXT) was discarded at both per-document catch sites
(document_ingestion.py's S3-backed `_load` and the inline-base64 branch in the main loop).
This converts the EXTRACTION_QUALITY_FAILED trigger from inference into a measurement. `.code`
stays canonical everywhere; `.reason_code`/`extraction_error_reason` is strictly additive.
"""
import base64

import pytest

from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ingestion import process_attachments


def _reference(ehr_resource_id, attachments, date="2026-01-01T00:00:00Z"):
    from types import SimpleNamespace
    return SimpleNamespace(
        ehr_resource_id=ehr_resource_id,
        data={"attachments": attachments, "type": "Document", "date": date},
    )


class FakeStorage:
    def __init__(self, content_by_path):
        self._content_by_path = content_by_path

    async def download_document(self, file_path: str) -> bytes:
        return self._content_by_path[file_path]


class RaisingExtractor:
    """Always raises the given DocumentProcessingError, mimicking a sanitize-gate rejection."""

    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self, reason_code="INVALID_TEXT"):
        self.reason_code = reason_code

    async def extract_text_async(self, content, content_type, file_name=None) -> str:
        raise DocumentProcessingError(self.reason_code)


@pytest.mark.asyncio
async def test_s3_backed_path_persists_reason_code_alongside_canonical_code():
    """The `_load` concurrent-pass site (document_ingestion.py ~:104)."""
    storage = FakeStorage({"a.txt": b"irrelevant"})
    extractor = RaisingExtractor("INVALID_TEXT")
    references = [_reference("docref-A", [{
        "filePath": "a.txt", "checksum": "csum-1", "downloadStatus": "success",
        "contentType": "text/plain", "title": "Admission Note", "fileName": "a.txt",
    }])]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    # .code stays canonical: INVALID_TEXT groups under EXTRACTION_QUALITY_FAILED.
    assert result[0].extraction_error == "EXTRACTION_QUALITY_FAILED"
    assert result[0].extraction_error_reason == "INVALID_TEXT"


@pytest.mark.asyncio
async def test_inline_base64_path_persists_reason_code_alongside_canonical_code():
    """The inline/sequential-path site (document_ingestion.py ~:205)."""
    storage = FakeStorage({})
    extractor = RaisingExtractor("INVALID_TEXT")
    inline_payload = base64.b64encode(b"irrelevant").decode()
    references = [_reference("docref-A", [{
        "filePath": "", "checksum": "", "downloadStatus": None,
        "contentType": "text/plain", "title": "Admission Note", "fileName": "a.txt",
        "data": inline_payload,
    }])]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert result[0].extraction_error == "EXTRACTION_QUALITY_FAILED"
    assert result[0].extraction_error_reason == "INVALID_TEXT"


@pytest.mark.asyncio
async def test_generic_exception_still_sets_reason_for_internal_processing_error():
    """Non-DocumentProcessingError failures still get a reason (INTERNAL_PROCESSING_ERROR),
    for consistency with the rest of this field -- no caller may assume it's always populated
    only from DocumentProcessingError.
    """
    storage = FakeStorage({"a.txt": b"irrelevant"})

    class BoomExtractor:
        MAX_FILE_SIZE = 50 * 1024 * 1024

        async def extract_text_async(self, content, content_type, file_name=None) -> str:
            raise RuntimeError("boom")

    references = [_reference("docref-A", [{
        "filePath": "a.txt", "checksum": "csum-1", "downloadStatus": "success",
        "contentType": "text/plain", "title": "Doc", "fileName": "a.txt",
    }])]

    result = await process_attachments(references, storage, BoomExtractor())

    assert result[0].extraction_error == "INTERNAL_PROCESSING_ERROR"
    assert result[0].extraction_error_reason == "INTERNAL_PROCESSING_ERROR"


@pytest.mark.asyncio
async def test_successful_extraction_leaves_reason_unset():
    class FakeExtractor:
        MAX_FILE_SIZE = 50 * 1024 * 1024

        async def extract_text_async(self, content, content_type, file_name=None) -> str:
            return "clean clinical text"

    storage = FakeStorage({"a.txt": b"irrelevant"})
    references = [_reference("docref-A", [{
        "filePath": "a.txt", "checksum": "csum-1", "downloadStatus": "success",
        "contentType": "text/plain", "title": "Doc", "fileName": "a.txt",
    }])]

    result = await process_attachments(references, storage, FakeExtractor())

    assert result[0].extraction_error is None
    assert result[0].extraction_error_reason is None
