"""Regression test for round9-revision3.md S3.3 step 5d / risk R13 (F8; required regression
test #8 of the task's required list).

Before F8: `source_fingerprint` was only written when `processing_outcome == "complete"`
(`attachment_summarization.py`). A `partial` outcome -- including one whose ONLY error class is
the order-then-cap truncation sentinel introduced by F3/F7 -- never got fingerprinted, and
`summary_cache.py` requires `complete` for a cache hit. Since truncation is deterministic given
the same manifest AND the same total ordering (the `ehr_resource_id` final tiebreak in
`fhir_resources.py`'s SELECTION query, F3 step 2), the four heaviest encounters would otherwise
re-run the ENTIRE ingestion + map/reduce + grounding pipeline on every refresh, forever, uncached
-- on exactly the encounters that are the most expensive to re-run.

This test drives `AttachmentSummarizationService.analyze_attachments` through a full run where
one of two extracted documents carries the F7 canonical truncation sentinel and the other
succeeds, and asserts `source_fingerprint` IS written to the persisted `partial` outcome.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.app.models.attachment_summarization import (
    AttachmentSummarizationRequest,
    AttachmentSummarizationResponse,
)
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)
from src.app.services.validated_summary import seal_summary


def _request():
    return AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())


def _appointment():
    return SimpleNamespace(
        appointment_date=datetime(2026, 1, 1),
        purpose="Follow-up",
        ehr_entity_id="enc-123",
        provider_id=None,
    )


class _FakeSummariesRepo:
    def __init__(self):
        self.upsert_calls = []

    async def upsert(self, appointment_id, summary_data):
        self.upsert_calls.append((appointment_id, summary_data))
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=uuid4(), appointment_id=appointment_id, created_at=now, updated_at=now,
            **summary_data,
        )


def _service():
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.logger = SimpleNamespace(
        info=lambda *a, **k: None, debug=lambda *a, **k: None,
        warning=lambda *a, **k: None, error=lambda *a, **k: None,
    )
    service.summaries_repo = _FakeSummariesRepo()
    service.fhir_repo = SimpleNamespace()
    service.s3_client = SimpleNamespace(validate_download_versions=_async_noop)
    return service


async def _async_noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_source_fingerprint_is_written_for_a_partial_outcome_whose_only_error_is_truncation(
    monkeypatch,
):
    service = _service()
    request = _request()
    appointment = _appointment()
    doc_references = [SimpleNamespace(ehr_resource_id="doc-1", data={}, updated_at=None)]

    # F7's canonical sentinel, constructed exactly as document_ingestion.py now does it (via
    # DocumentProcessingError, so .code/.reason_code are the real canonicalized pair).
    sentinel = DocumentProcessingError("DOCUMENT_LIMIT_EXCEEDED")
    successful_doc = SimpleNamespace(
        extraction_error=None, extraction_error_reason=None, resource_id="ok-doc",
        title="Visit Note", content_type="text/html", file_name="a.html", size=10,
        date=None, document_type="Document", content_sha256="s1", parsed_text_sha256="p1",
        parser_version="v1",
    )
    truncated_placeholder = SimpleNamespace(
        extraction_error=sentinel.code, extraction_error_reason=sentinel.reason_code,
        resource_id="truncated-doc", title=None, content_type="application/octet-stream",
        file_name=None, size=None, date=None, document_type=None, content_sha256=None,
        parsed_text_sha256=None, parser_version=None,
    )
    extracted = [successful_doc, truncated_placeholder]

    analysis_result = seal_summary(
        AttachmentSummarizationResponse(
            clinical_summary="Patient summary text, grounded in the one successfully extracted document.",
            documents_analyzed=1,
        )
    )

    async def fake_fetch_appointment_details(req):
        return appointment, "Dr. Smith"

    async def fake_fetch_document_references(req, appt):
        return doc_references

    async def fake_process_attachments(refs):
        return extracted

    async def fake_run_ai_analysis(appointment_context, documents, *, encounter_id=None):
        return analysis_result

    monkeypatch.setattr(service, "_fetch_appointment_details", fake_fetch_appointment_details)
    monkeypatch.setattr(service, "_fetch_document_references", fake_fetch_document_references)
    monkeypatch.setattr(service, "_process_attachments", fake_process_attachments)
    monkeypatch.setattr(service, "_run_ai_analysis", fake_run_ai_analysis)
    monkeypatch.setattr(
        "src.app.services.summary_cache.attachment_fingerprint",
        lambda *a, **k: "fp-deterministic-truncation",
    )
    monkeypatch.setattr(
        "src.app.services.summary_cache.verified_attachment_cache",
        _async_cache_miss,
    )

    result = await service.analyze_attachments(request)

    assert result is not None
    assert len(service.summaries_repo.upsert_calls) == 1
    _, summary_data = service.summaries_repo.upsert_calls[0]
    metadata = summary_data["summary_metadata"]

    assert metadata["processing_outcome"] == "partial"
    assert len(metadata["extraction_errors"]) == 1
    assert metadata["extraction_errors"][0]["error"] == "RESOURCE_LIMIT_EXCEEDED"
    assert metadata["extraction_errors"][0]["reason"] == "DOCUMENT_LIMIT_EXCEEDED"
    # F8: the fingerprint IS written despite the outcome being `partial`, not `complete`,
    # because the only error class present is the deterministic truncation sentinel.
    assert metadata.get("source_fingerprint") == "fp-deterministic-truncation"


@pytest.mark.asyncio
async def test_source_fingerprint_withheld_for_a_partial_outcome_with_a_non_truncation_error(
    monkeypatch,
):
    """Control case: F8's widening must NOT apply when a `partial` outcome's error set
    contains anything other than the truncation sentinel -- those failures are not known to be
    deterministic, so caching them would risk serving a stale/wrong summary on a re-run that
    would otherwise have succeeded."""
    service = _service()
    request = _request()
    appointment = _appointment()
    doc_references = [SimpleNamespace(ehr_resource_id="doc-1", data={}, updated_at=None)]

    successful_doc = SimpleNamespace(
        extraction_error=None, extraction_error_reason=None, resource_id="ok-doc",
        title="Visit Note", content_type="text/html", file_name="a.html", size=10,
        date=None, document_type="Document", content_sha256="s1", parsed_text_sha256="p1",
        parser_version="v1",
    )
    unrelated_failure = SimpleNamespace(
        extraction_error="EXTRACTION_QUALITY_FAILED", extraction_error_reason="INVALID_TEXT",
        resource_id="bad-doc", title=None, content_type="text/plain", file_name=None,
        size=None, date=None, document_type=None, content_sha256=None,
        parsed_text_sha256=None, parser_version=None,
    )
    extracted = [successful_doc, unrelated_failure]

    analysis_result = seal_summary(
        AttachmentSummarizationResponse(
            clinical_summary="Patient summary text.", documents_analyzed=1,
        )
    )

    async def fake_fetch_appointment_details(req):
        return appointment, "Dr. Smith"

    async def fake_fetch_document_references(req, appt):
        return doc_references

    async def fake_process_attachments(refs):
        return extracted

    async def fake_run_ai_analysis(appointment_context, documents, *, encounter_id=None):
        return analysis_result

    monkeypatch.setattr(service, "_fetch_appointment_details", fake_fetch_appointment_details)
    monkeypatch.setattr(service, "_fetch_document_references", fake_fetch_document_references)
    monkeypatch.setattr(service, "_process_attachments", fake_process_attachments)
    monkeypatch.setattr(service, "_run_ai_analysis", fake_run_ai_analysis)
    monkeypatch.setattr(
        "src.app.services.summary_cache.attachment_fingerprint",
        lambda *a, **k: "fp-should-not-be-persisted",
    )
    monkeypatch.setattr(
        "src.app.services.summary_cache.verified_attachment_cache",
        _async_cache_miss,
    )

    await service.analyze_attachments(request)

    _, summary_data = service.summaries_repo.upsert_calls[0]
    metadata = summary_data["summary_metadata"]

    assert metadata["processing_outcome"] == "partial"
    assert "source_fingerprint" not in metadata


async def _async_cache_miss(*args, **kwargs):
    return None
