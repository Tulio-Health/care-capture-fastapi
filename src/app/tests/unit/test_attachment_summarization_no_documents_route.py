"""Unit tests for the `NO_DOCUMENTS` -> `no_documents` terminal-state routing at
`AttachmentSummarizationService.analyze_attachments`'s generic chain-exception catch site.

Fix 4 (round9-revision3.md Sec 3.4): when every document already failed extraction
individually, `AttachmentSummarizationChain.analyze` now raises
`DocumentProcessingError("NO_DOCUMENTS")` instead of a bare `ValueError`. This catch site must
route that specific code to the EXISTING `no_documents` terminal state (same shape as
`_static_fallback_summary_data`) as ONE batch-level outcome -- not the generic `unavailable`
row, and not fanned out as N per-document error rows.

The guard: `NO_DOCUMENTS` is registered in neither `_ERROR_CODE_GROUPS` nor `STAGES`, so the
emitted outcome must carry ZERO error rows -- `describe_error` must never be invoked with it.
If it were, `processing_errors.py`'s coercion would relabel it `INTERNAL_PROCESSING_ERROR`,
recreating the exact bug this fix removes.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)
from src.app.services.summary_outcomes import MESSAGES


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
            id=uuid4(),
            appointment_id=appointment_id,
            created_at=now,
            updated_at=now,
            **summary_data,
        )


def _service():
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.logger = SimpleNamespace(
        info=lambda *a, **k: None, debug=lambda *a, **k: None, warning=lambda *a, **k: None
    )
    service.summaries_repo = _FakeSummariesRepo()
    service.fhir_repo = SimpleNamespace()
    return service


async def _run_to_no_documents(monkeypatch, service, request):
    appointment = _appointment()
    extracted = [
        SimpleNamespace(extraction_error="EXTRACTION_QUALITY_FAILED", content_sha256="x"),
        SimpleNamespace(extraction_error="OCR_UNREADABLE", content_sha256="y"),
    ]

    async def fake_fetch_appointment_details(req):
        return appointment, "Dr. Smith"

    async def fake_fetch_document_references(req, appt):
        return [SimpleNamespace(ehr_resource_id="doc-1", data={}, updated_at=None)]

    async def fake_process_attachments(doc_references):
        return extracted

    async def fake_run_ai_analysis(appointment_context, documents, *, encounter_id=None):
        raise DocumentProcessingError("NO_DOCUMENTS")

    monkeypatch.setattr(service, "_fetch_appointment_details", fake_fetch_appointment_details)
    monkeypatch.setattr(service, "_fetch_document_references", fake_fetch_document_references)
    monkeypatch.setattr(service, "_process_attachments", fake_process_attachments)
    monkeypatch.setattr(service, "_run_ai_analysis", fake_run_ai_analysis)
    # Bypass the cache subsystem entirely -- this test is about the except-block routing, not
    # fingerprinting. (Every document here already carries extraction_error, which already
    # makes the real attachment_fingerprint return None, but patching keeps the test isolated
    # from that module's own logic/settings dependency.)
    monkeypatch.setattr("src.app.services.summary_cache.attachment_fingerprint", lambda *a, **k: None)

    return await service.analyze_attachments(request), extracted


@pytest.mark.asyncio
async def test_no_documents_reason_code_writes_no_documents_row_once(monkeypatch):
    service = _service()
    request = _request()

    result, extracted = await _run_to_no_documents(monkeypatch, service, request)

    assert result is not None
    assert len(service.summaries_repo.upsert_calls) == 1  # batch-level, never fanned out
    appointment_id, summary_data = service.summaries_repo.upsert_calls[0]
    assert appointment_id == request.appointment_id
    assert summary_data["summary_text"] == MESSAGES["no_documents"]
    metadata = summary_data["summary_metadata"]
    assert metadata["processing_outcome"] == "no_documents"
    assert metadata["total_documents"] == len(extracted)
    assert metadata["failed_documents"] == len(extracted)
    assert metadata["successful_documents"] == 0


@pytest.mark.asyncio
async def test_no_documents_route_emits_zero_error_rows_and_never_calls_describe_error(monkeypatch):
    """Guard required by Fix 4: NO_DOCUMENTS is registered in neither _ERROR_CODE_GROUPS nor
    STAGES, so if describe_error were ever called with it, processing_errors.py's coercion
    would relabel it INTERNAL_PROCESSING_ERROR -- recreating the exact bug this fix removes."""
    service = _service()
    request = _request()

    def fail_if_called(code, source_id=None, reason=None):
        raise AssertionError(
            f"describe_error must never be called on the no_documents route (got code={code!r})"
        )

    monkeypatch.setattr("src.app.services.processing_errors.describe_error", fail_if_called)

    await _run_to_no_documents(monkeypatch, service, request)

    _, summary_data = service.summaries_repo.upsert_calls[0]
    metadata = summary_data["summary_metadata"]
    assert metadata["processing_errors"] == []
    assert metadata["processing_error_count"] == 0
