"""Unit tests for the "no attachment text could be extracted" outcome of
`AttachmentSummarizationService.analyze_attachments`.

Prior behavior: when `_process_attachments` returned an empty list, the service raised a bare
`ValueError`, which the route handler converts into an uncaught-looking `HTTPException(400)` with
no `conversation_summaries` row ever written -- indistinguishable downstream from "summary never
attempted". Fixed behavior: the service now writes an `unavailable` row (same shape/mechanism as
the sibling `_fetch_document_references` exception-catch branch a few lines above it) and returns
normally, so the route returns its normal 2xx response.

The appointment-not-found `ValueError` (raised in `_fetch_appointment_details`) is a distinct,
legitimate "bad request" case and must keep propagating uncaught (no row written) -- covered here
too as a regression guard.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)
from src.app.services.summary_outcomes import MESSAGES
from src.app.models.attachment_summarization import AttachmentSummarizationRequest


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


@pytest.mark.asyncio
async def test_no_extracted_text_writes_unavailable_row_instead_of_raising(monkeypatch):
    appointment = _appointment()
    request = _request()
    service = _service()

    async def fake_fetch_appointment_details(req):
        return appointment, "Dr. Smith"

    async def fake_fetch_document_references(req, appt):
        return [SimpleNamespace(ehr_resource_id="doc-1", data={}, updated_at=None)]

    async def fake_process_attachments(doc_references):
        return []

    monkeypatch.setattr(service, "_fetch_appointment_details", fake_fetch_appointment_details)
    monkeypatch.setattr(service, "_fetch_document_references", fake_fetch_document_references)
    monkeypatch.setattr(service, "_process_attachments", fake_process_attachments)

    result = await service.analyze_attachments(request)

    assert len(service.summaries_repo.upsert_calls) == 1
    appointment_id, summary_data = service.summaries_repo.upsert_calls[0]
    assert appointment_id == request.appointment_id
    assert summary_data["summary_text"] == MESSAGES["unavailable"]
    assert summary_data["summary_metadata"]["processing_outcome"] == "unavailable"
    assert result is not None


@pytest.mark.asyncio
async def test_appointment_not_found_still_raises_value_error_with_no_row_written():
    """Regression guard: this ValueError case is out of scope and must be unaffected."""
    service = _service()

    async def fake_fetch_appointment_details(req):
        raise ValueError(f"Appointment {req.appointment_id} not found")

    service._fetch_appointment_details = fake_fetch_appointment_details

    with pytest.raises(ValueError, match="not found"):
        await service.analyze_attachments(_request())

    assert service.summaries_repo.upsert_calls == []
