"""Unit tests for checksum-based attachment dedup in `process_attachments`.

Real production data (see `care-capture-nodeapi` debug report
`2026-09-17-document-scope-question/duplicate-documents-root-cause-and-fix.md`) shows Epic
issues byte-identical document content under distinct `DocumentReference` ids. Duplicates were
fully downloaded/extracted/sent to the LLM, wasting budget on exactly the largest appointments
already at risk of `MODEL_CALL_BUDGET_EXCEEDED`. These tests guard the fix: a per-call
checksum -> kept-resource map that skips re-processing byte-identical attachments, without ever
marking the dropped copy with an `extraction_error` (which would disable the content-verified
summary cache, see `attachment_summarization.py`'s `all(... not d.extraction_error ...)` gate).
"""
from types import SimpleNamespace

import pytest

from src.app.services.document_ingestion import process_attachments
from src.app.services.summary_cache import attachment_fingerprint


def _reference(ehr_resource_id, attachments, date="2026-01-01T00:00:00Z"):
    return SimpleNamespace(
        ehr_resource_id=ehr_resource_id,
        data={"attachments": attachments, "type": "Document", "date": date},
    )


def _attachment(file_path, checksum="", download_status="success", content_type="text/html"):
    return {
        "filePath": file_path,
        "checksum": checksum,
        "downloadStatus": download_status,
        "contentType": content_type,
        "title": "Doc",
        "fileName": file_path,
    }


class FakeStorage:
    """Mocks S3DocumentClient.download_document; content keyed by path."""

    def __init__(self, content_by_path):
        self._content_by_path = content_by_path
        self.calls = []

    async def download_document(self, file_path: str) -> bytes:
        self.calls.append(file_path)
        return self._content_by_path[file_path]


class FakeExtractor:
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self):
        self.calls = []

    async def extract_text_async(self, content, content_type, file_name=None) -> str:
        self.calls.append(file_name)
        return f"extracted:{content.decode()}"


@pytest.mark.asyncio
async def test_same_checksum_dedups_and_skips_second_download():
    """Case 1: identical checksum -> only one DocumentAttachment, only one S3 GET."""
    storage = FakeStorage({"a.html": b"same-bytes", "b.html": b"same-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [_attachment("a.html", checksum="csum-1")]),
        _reference("docref-B", [_attachment("b.html", checksum="csum-1")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert storage.calls == ["a.html"]
    assert extractor.calls == ["a.html"]
    assert result[0].extraction_error is None


@pytest.mark.asyncio
async def test_different_checksums_both_survive():
    """Case 2: distinct checksums -> no over-dedup, both downloaded and processed."""
    storage = FakeStorage({"a.html": b"content-A", "b.html": b"content-B"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [_attachment("a.html", checksum="csum-1")]),
        _reference("docref-B", [_attachment("b.html", checksum="csum-2")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 2
    assert storage.calls == ["a.html", "b.html"]
    assert {d.extraction_error for d in result} == {None}


@pytest.mark.asyncio
async def test_failed_download_never_deduped_even_with_matching_checksum():
    """Case 3: downloadStatus != success (or empty checksum) must never act as a dedup key,
    even if it coincidentally matches another attachment's checksum. It keeps its existing
    DOCUMENT_NOT_READY failure path, and does not suppress a later real duplicate check either.
    """
    storage = FakeStorage({"b.html": b"same-bytes"})
    extractor = FakeExtractor()
    references = [
        # "failed" download: has a path but downloadStatus != success -> DOCUMENT_NOT_READY.
        _reference("docref-A", [_attachment("a.html", checksum="csum-1", download_status="failed")]),
        # Legitimate success with the same checksum value - must NOT be skipped, since the
        # failed attachment's checksum was never trusted/recorded as "seen".
        _reference("docref-B", [_attachment("b.html", checksum="csum-1", download_status="success")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 2
    failed = next(d for d in result if d.extraction_error is not None)
    succeeded = next(d for d in result if d.extraction_error is None)
    # DOCUMENT_NOT_READY is DocumentProcessingError's canonical public code for this reason
    # (see the `groups` mapping in document_extraction.py); `.reason_code` keeps the raw one.
    assert failed.extraction_error == "DOWNLOAD_PENDING"
    assert failed.extraction_error != "DOCUMENT_LIMIT_EXCEEDED"
    assert storage.calls == ["b.html"]
    assert succeeded.content_sha256 is not None


@pytest.mark.asyncio
async def test_empty_checksum_never_deduped():
    """An attachment with no checksum at all (empty string) must never be treated as a dedup
    key, even against another attachment that also happens to have an empty checksum.
    """
    storage = FakeStorage({"a.html": b"content-A", "b.html": b"content-A"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [_attachment("a.html", checksum="")]),
        _reference("docref-B", [_attachment("b.html", checksum="")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 2
    assert storage.calls == ["a.html", "b.html"]


@pytest.mark.asyncio
async def test_duplicate_drop_sets_no_extraction_error_and_preserves_fingerprint_gate():
    """Case 4: the dropped duplicate must be invisible to attachment_summarization.py's
    `all(d.content_sha256 and not d.extraction_error for d in extracted_documents)` cache gate -
    it is simply absent from the returned list, not present-with-an-error. Confirmed here by
    calling the real `attachment_fingerprint` helper (the actual cache-key function) against the
    deduped result and asserting it still returns a real fingerprint, exactly as if only the
    unique document had ever existed.
    """
    storage = FakeStorage({"a.html": b"same-bytes", "b.html": b"same-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [_attachment("a.html", checksum="csum-1")]),
        _reference("docref-B", [_attachment("b.html", checksum="csum-1")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert all(d.extraction_error is None for d in result)
    assert all(d.content_sha256 for d in result)

    settings = SimpleNamespace(
        DOCUMENT_VERIFICATION_MODEL="test", DOCUMENT_OCR_MODEL="test", ENABLE_DOCUMENT_OCR=False,
    )
    fingerprint = attachment_fingerprint(result, manifest={}, context={}, settings=settings)

    assert fingerprint is not None


@pytest.mark.asyncio
async def test_inline_base64_fallback_dedup_on_content_sha256():
    """Inline (base64) attachments carry no vendor checksum field, so the fallback tier keys on
    the content_sha256 we compute ourselves, applied after decoding but before the expensive
    extract_text_async call.
    """
    import base64

    storage = FakeStorage({})
    extractor = FakeExtractor()
    inline_payload = base64.b64encode(b"same-inline-bytes").decode()
    references = [
        _reference("docref-A", [{
            "filePath": "", "checksum": "", "downloadStatus": None,
            "contentType": "text/plain", "title": "Doc", "fileName": "a.txt", "data": inline_payload,
        }]),
        _reference("docref-B", [{
            "filePath": "", "checksum": "", "downloadStatus": None,
            "contentType": "text/plain", "title": "Doc", "fileName": "b.txt", "data": inline_payload,
        }]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert extractor.calls == ["a.txt"]
    assert storage.calls == []


@pytest.mark.asyncio
async def test_max_documents_cap_counts_unique_documents():
    """A duplicate dropped before append does not consume a MAX_DOCUMENTS slot - the cap
    counts unique documents, strictly better than before (more room for real distinct content).
    """
    from src.app.services.document_ingestion import MAX_DOCUMENTS

    storage = FakeStorage({"dup-a.html": b"same-bytes", "dup-b.html": b"same-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-dup-A", [_attachment("dup-a.html", checksum="csum-dup")]),
        _reference("docref-dup-B", [_attachment("dup-b.html", checksum="csum-dup")]),
    ]
    for i in range(MAX_DOCUMENTS):
        path = f"unique-{i}.html"
        storage._content_by_path[path] = f"content-{i}".encode()
        references.append(_reference(f"docref-unique-{i}", [_attachment(path, checksum=f"csum-{i}")]))

    result = await process_attachments(references, storage, extractor)

    # dup-a (kept) + 100 unique documents fill every real slot; the 101st attachment then hits
    # the cap and becomes the truncation sentinel appended on top - so the returned list is
    # MAX_DOCUMENTS unique real documents + 1 sentinel, and the deduped dup-b never even reaches
    # (and therefore never occupies) a slot.
    # F7 (round9-revision3.md S3.3 step 5b / risk R14): the sentinel's .extraction_error is now
    # the CANONICAL RESOURCE_LIMIT_EXCEEDED code (DOCUMENT_LIMIT_EXCEEDED is a group MEMBER, not
    # a processing_errors.STAGES key -- the pre-F7 raw string here coerced to
    # INTERNAL_PROCESSING_ERROR in describe_error, recreating the exact defect Fix 4 removed).
    # The specific code now rides on the additive .extraction_error_reason sibling instead.
    assert len(result) == MAX_DOCUMENTS + 1
    assert result[-1].extraction_error == "RESOURCE_LIMIT_EXCEEDED"
    assert result[-1].extraction_error_reason == "DOCUMENT_LIMIT_EXCEEDED"
    assert "dup-b.html" not in storage.calls


@pytest.mark.asyncio
async def test_max_documents_sentinel_never_describes_as_internal_processing_error():
    """resolves rt2-truncation-sentinel-coerces-to-internal (round9-revision3.md S3.3 step 5b /
    risk R14) -- the specific regression F7 exists to prevent. Before F7, document_ingestion.py:128
    wrote the raw group-member string "DOCUMENT_LIMIT_EXCEEDED" directly (bypassing
    DocumentProcessingError's canonicalization), which is not a processing_errors.STAGES key, so
    describe_error() coerced it to INTERNAL_PROCESSING_ERROR -- silently mislabeling the exact
    truncation path Fix 5 makes live. Asserts describe_error() applied to the real sentinel this
    module produces NEVER returns INTERNAL_PROCESSING_ERROR.
    """
    from src.app.services.document_ingestion import MAX_DOCUMENTS
    from src.app.services.processing_errors import describe_error

    storage = FakeStorage({})
    extractor = FakeExtractor()
    references = []
    for i in range(MAX_DOCUMENTS + 1):
        path = f"doc-{i}.html"
        storage._content_by_path[path] = f"content-{i}".encode()
        references.append(_reference(f"docref-{i}", [_attachment(path, checksum=f"csum-{i}")]))

    result = await process_attachments(references, storage, extractor)
    sentinel = result[-1]

    described = describe_error(sentinel.extraction_error, reason=sentinel.extraction_error_reason)

    assert described["error"] == "RESOURCE_LIMIT_EXCEEDED"
    assert described["error"] != "INTERNAL_PROCESSING_ERROR"
    assert described["reason"] == "DOCUMENT_LIMIT_EXCEEDED"
