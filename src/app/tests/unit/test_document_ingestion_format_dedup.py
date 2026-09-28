"""Unit tests for within-DocumentReference format-preference dedup in `process_attachments`.

Real production data (see `care-capture-nodeapi` debug report
`2026-09-17-document-scope-question/document-scope-research.md`) shows a single
`DocumentReference` frequently carries multiple `attachments[]` entries that represent the SAME
underlying clinical note in different file formats (html+rtf, pdf+xml) -- these are NOT
byte-identical (different formats = different bytes), so the checksum-based dedup in
`test_document_ingestion_dedup.py` cannot catch them. This is a distinct, larger duplication
mechanism scoped specifically to multiple attachments within one DocumentReference; FHIR's own
data model already asserts they're representations of one logical document, which is why no
content/checksum comparison is required here -- just pick the best format and drop the rest.

These tests guard the fix: a per-reference format-preference selection that, when 2+ attachments
on the same DocumentReference have `downloadStatus == "success"`, processes only the
most-preferred format and skips the rest entirely -- never marking the dropped copies with an
`extraction_error` (which would disable the content-verified summary cache gate, see
`attachment_summarization.py`'s `all(... not d.extraction_error ...)` gate).
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


def _attachment(file_path, content_type, checksum="", download_status="success"):
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
async def test_html_rtf_pair_only_processes_preferred_html_format():
    """Case 1: html + rtf, both downloadStatus success -> only html (preferred) is downloaded
    and processed; rtf never triggers an S3 GET, confirmed via download-call-count, not just
    returned-list length.
    """
    storage = FakeStorage({"note.html": b"note-html-bytes", "note.rtf": b"note-rtf-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [
            _attachment("note.html", "text/html"),
            _attachment("note.rtf", "text/rtf"),
        ]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert storage.calls == ["note.html"]
    assert extractor.calls == ["note.html"]
    assert result[0].content_type == "text/html"
    assert result[0].extraction_error is None


@pytest.mark.asyncio
async def test_pdf_xml_pair_only_processes_preferred_pdf_format():
    """Same reduction for the other observed real combination: pdf beats xml (real prod xml
    exports bury the narrative as an undecoded base64 blob inside mostly administrative noise).
    """
    storage = FakeStorage({"report.pdf": b"pdf-bytes", "report.xml": b"xml-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [
            _attachment("report.pdf", "application/pdf"),
            _attachment("report.xml", "application/xml"),
        ]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert storage.calls == ["report.pdf"]
    assert result[0].content_type == "application/pdf"


@pytest.mark.asyncio
async def test_preferred_format_failed_falls_back_to_other_available_attachment():
    """Case 2: the preferred-format (html) attachment failed to download -> the reduction must
    not trigger (only 1 successful attachment remains), so the other available format (rtf) is
    still processed instead of ending up with nothing.
    """
    storage = FakeStorage({"note.rtf": b"note-rtf-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [
            _attachment("note.html", "text/html", download_status="failed"),
            _attachment("note.rtf", "text/rtf", download_status="success"),
        ]),
    ]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 2
    failed = next(d for d in result if d.extraction_error is not None)
    succeeded = next(d for d in result if d.extraction_error is None)
    assert failed.extraction_error == "DOWNLOAD_PENDING"
    assert succeeded.content_type == "text/rtf"
    assert storage.calls == ["note.rtf"]


@pytest.mark.asyncio
async def test_single_attachment_reference_unaffected():
    """Case 3: only one attachment on the DocumentReference -> no regression, processes
    normally regardless of content type.
    """
    storage = FakeStorage({"note.html": b"note-html-bytes"})
    extractor = FakeExtractor()
    references = [_reference("docref-A", [_attachment("note.html", "text/html")])]

    result = await process_attachments(references, storage, extractor)

    assert len(result) == 1
    assert storage.calls == ["note.html"]
    assert result[0].extraction_error is None


@pytest.mark.asyncio
async def test_composes_with_checksum_dedup_across_resources():
    """Case 4: a within-resource format-duplicate (html+rtf on docref-A) AND a cross-resource
    byte-identical duplicate (docref-B and docref-C both html, identical checksum) in the same
    appointment -- both reductions apply together. Expect exactly one surviving document.
    """
    storage = FakeStorage({
        "a-note.html": b"same-bytes",
        "a-note.rtf": b"a-rtf-bytes",
        "b-note.html": b"same-bytes",
    })
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [
            _attachment("a-note.html", "text/html", checksum="csum-shared"),
            _attachment("a-note.rtf", "text/rtf", checksum="csum-rtf"),
        ]),
        _reference("docref-B", [
            _attachment("b-note.html", "text/html", checksum="csum-shared"),
        ]),
    ]

    result = await process_attachments(references, storage, extractor)

    # docref-A's rtf is dropped by format-dedup; docref-A's html (kept) and docref-B's html are
    # checksum-identical, so docref-B's html is dropped by the pre-existing checksum dedup.
    assert len(result) == 1
    assert storage.calls == ["a-note.html"]
    assert result[0].content_type == "text/html"


@pytest.mark.asyncio
async def test_dropped_format_duplicate_sets_no_extraction_error_and_preserves_fingerprint_gate():
    """Dropped format-duplicates must be invisible to attachment_summarization.py's cache gate --
    absent from the returned list, never present-with-an-error. Confirmed by calling the real
    `attachment_fingerprint` helper against the reduced result.
    """
    storage = FakeStorage({"note.html": b"note-html-bytes", "note.rtf": b"note-rtf-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-A", [
            _attachment("note.html", "text/html"),
            _attachment("note.rtf", "text/rtf"),
        ]),
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
async def test_max_documents_cap_counts_format_deduped_documents_as_one():
    """A format-duplicate dropped before append does not consume a MAX_DOCUMENTS slot, same
    strict-improvement property as the checksum dedup. Mirrors the checksum dedup's own cap test
    shape: 1 format-dup pair (1 kept) + MAX_DOCUMENTS unique attachments = 101 real attempts, so
    the 101st (last) attempt hits the cap and becomes the sentinel -- proving the dropped rtf
    copy never consumed a slot.
    """
    from src.app.services.document_ingestion import MAX_DOCUMENTS

    storage = FakeStorage({"dup.html": b"html-bytes", "dup.rtf": b"rtf-bytes"})
    extractor = FakeExtractor()
    references = [
        _reference("docref-dup", [
            _attachment("dup.html", "text/html"),
            _attachment("dup.rtf", "text/rtf"),
        ]),
    ]
    for i in range(MAX_DOCUMENTS):
        path = f"unique-{i}.html"
        storage._content_by_path[path] = f"content-{i}".encode()
        references.append(_reference(f"docref-unique-{i}", [_attachment(path, "text/html", checksum=f"csum-{i}")]))

    result = await process_attachments(references, storage, extractor)

    assert len(result) == MAX_DOCUMENTS + 1
    assert result[-1].extraction_error == "DOCUMENT_LIMIT_EXCEEDED"
    assert "dup.rtf" not in storage.calls
