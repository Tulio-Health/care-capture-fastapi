"""Unit tests for Pass-A/Pass-B parallelized ingestion in `process_attachments`
(topic-D parallelize-and-sizing, Change 1). S3-backed attachments' download + extraction now run
concurrently via `asyncio.gather` (`_load` mutates each `DocumentAttachment` in place at its
already-fixed `result` position). These tests prove:
  1. multiple S3-backed attachments really do run concurrently (in-flight overlap, not
     one-at-a-time), and out-of-order completion never scrambles `result`'s order;
  2. a mix of S3-backed and inline attachments still dedups inline content sequentially while
     S3-backed ones parallelize around it, in the original reference order.
"""
import asyncio
from types import SimpleNamespace

import pytest

from src.app.services.document_ingestion import process_attachments


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


class SlowStorage:
    """Mocks S3DocumentClient.download_document with a configurable per-path delay, so the
    fastest download can complete before a slower one that was *requested* earlier -- proving
    the final `result` order does not depend on completion order.
    """

    def __init__(self, content_by_path, delay_by_path):
        self._content_by_path = content_by_path
        self._delay_by_path = delay_by_path
        self.calls = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def download_document(self, file_path: str) -> bytes:
        self.calls.append(file_path)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(self._delay_by_path.get(file_path, 0))
        self.in_flight -= 1
        return self._content_by_path[file_path]


class FakeExtractor:
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self):
        self.calls = []

    async def extract_text_async(self, content, content_type, file_name=None) -> str:
        self.calls.append(file_name)
        return f"extracted:{content.decode()}"


@pytest.mark.asyncio
async def test_s3_backed_downloads_overlap_concurrently():
    """Proves Change 1 actually parallelizes: with 4 attachments each sleeping 50ms, more than
    one download must be in-flight at once, or the same 4 downloads would take >=200ms serially.
    """
    storage = SlowStorage(
        content_by_path={f"doc-{i}.html": f"content-{i}".encode() for i in range(4)},
        delay_by_path={f"doc-{i}.html": 0.05 for i in range(4)},
    )
    extractor = FakeExtractor()
    references = [
        _reference(f"docref-{i}", [_attachment(f"doc-{i}.html", checksum=f"csum-{i}")])
        for i in range(4)
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 4
    assert all(d.extraction_error is None for d in result)
    # If these ran sequentially, in_flight would never exceed 1.
    assert storage.max_in_flight > 1


@pytest.mark.asyncio
async def test_out_of_order_completion_does_not_scramble_result_order():
    """The attachment requested FIRST is given the LONGEST delay and the one requested LAST
    finishes FIRST -- if `result` were built by appending whichever coroutine resolves first
    (the bug this parallelization must not introduce), doc-0 would end up last. It must instead
    stay first, matching the original reference order.
    """
    storage = SlowStorage(
        content_by_path={
            "doc-0.html": b"content-0",
            "doc-1.html": b"content-1",
            "doc-2.html": b"content-2",
        },
        delay_by_path={"doc-0.html": 0.06, "doc-1.html": 0.03, "doc-2.html": 0.0},
    )
    extractor = FakeExtractor()
    references = [
        _reference("docref-0", [_attachment("doc-0.html", checksum="csum-0")]),
        _reference("docref-1", [_attachment("doc-1.html", checksum="csum-1")]),
        _reference("docref-2", [_attachment("doc-2.html", checksum="csum-2")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert [d.file_path for d in result] == ["doc-0.html", "doc-1.html", "doc-2.html"]
    assert [d.extracted_text for d in result] == ["extracted:content-0", "extracted:content-1", "extracted:content-2"]


@pytest.mark.asyncio
async def test_mixed_inline_and_s3_backed_preserves_order_and_dedup():
    """A mix of S3-backed (parallelized) and inline (sequential, content-hash deduped)
    attachments in the same appointment: inline dedup must still correctly drop a duplicate
    inline attachment, and every survivor (S3-backed or inline) must land in original reference
    order in the final result.
    """
    import base64

    storage = SlowStorage(
        content_by_path={"doc-a.html": b"content-a", "doc-c.html": b"content-c"},
        delay_by_path={"doc-a.html": 0.02, "doc-c.html": 0.0},
    )
    extractor = FakeExtractor()
    inline_payload = base64.b64encode(b"same-inline-bytes").decode()
    references = [
        _reference("docref-a", [_attachment("doc-a.html", checksum="csum-a")]),
        _reference("docref-b1", [{
            "filePath": "", "checksum": "", "downloadStatus": None,
            "contentType": "text/plain", "title": "Doc", "fileName": "inline-1.txt",
            "data": inline_payload,
        }]),
        _reference("docref-b2", [{
            # Duplicate inline content of docref-b1 -- must still be dropped via the sequential
            # post-download content-hash dedup, not raced against the S3-backed downloads.
            "filePath": "", "checksum": "", "downloadStatus": None,
            "contentType": "text/plain", "title": "Doc", "fileName": "inline-2.txt",
            "data": inline_payload,
        }]),
        _reference("docref-c", [_attachment("doc-c.html", checksum="csum-c")]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert [d.file_path for d in result] == ["doc-a.html", "inline://" + result[1].resource_id, "doc-c.html"]
    assert len(result) == 3  # the duplicate inline attachment was dropped, not appended
    assert result[1].extracted_text == "extracted:same-inline-bytes"
    assert all(d.extraction_error is None for d in result)
