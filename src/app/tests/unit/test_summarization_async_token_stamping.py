"""Unit tests for the `async_token` stamping added to both summarization services'
persisted `summary_metadata` (round5-final.md section 5, care-capture-nodeapi sibling
repo): the value flows from `request.async_token` into every metadata-construction site
(additive JSON field), and is simply absent (None) for ordinary sync requests that never
set it -- this is what makes Node API's token-aware rescue read (section 7.3) work.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.app.chains.procedure_extraction.consolidation import ConsolidatedProcedure
from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummarizationRequest,
    ProcedureSummary,
)
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)
from src.app.services.summarization.procedure_summarization import (
    ProcedureSummarizationService,
)


def _appointment():
    return SimpleNamespace(
        appointment_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
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


def _attachment_service():
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        warning=lambda *a, **k: None,
    )
    service.summaries_repo = _FakeSummariesRepo()
    service.fhir_repo = SimpleNamespace()
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "async_token", ["tok-async-1", None], ids=["async-request", "sync-request-no-token"]
)
async def test_attachment_no_documents_fallback_stamps_async_token_from_request(
    async_token,
) -> None:
    """`_static_fallback_summary_data` (the no-documents-found row) is one of the two
    metadata-construction sites -- confirms the field round-trips exactly, including the
    sync-path case where it's simply absent."""
    service = _attachment_service()
    request = AttachmentSummarizationRequest(
        appointment_id=uuid4(), user_id=uuid4(), async_token=async_token
    )

    async def fake_fetch_appointment_details(req):
        return _appointment(), "Dr. Smith"

    async def fake_fetch_document_references(req, appt):
        return []

    service._fetch_appointment_details = fake_fetch_appointment_details
    service._fetch_document_references = fake_fetch_document_references

    await service.analyze_attachments(request)

    _, summary_data = service.summaries_repo.upsert_calls[0]
    assert summary_data["summary_metadata"]["async_token"] == async_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "async_token", ["tok-async-2", None], ids=["async-request", "sync-request-no-token"]
)
async def test_procedure_persist_stamps_async_token_on_each_consolidated_row(
    async_token,
) -> None:
    """`_persist`'s per-consolidated-procedure row-building is the other metadata-
    construction site (the main content path, not just the empty/fallback branches)."""
    service = ProcedureSummarizationService.__new__(ProcedureSummarizationService)
    service.logger = MagicMock()
    service.summaries_repo = MagicMock()
    service.summaries_repo.upsert_many_for_source = AsyncMock(return_value=[])

    summary = ProcedureSummary(
        source_document_title="Procedure Note",
        event_source_quote="Cardiac catheterization performed 2026-06-29",
        procedure_type="Cardiac catheterization",
        procedure_date="2026-06-29",
        performed_by=["Dr. A"],
        reason="You had chest pain.",
        procedure_details="A catheter was inserted to check your arteries.",
        outcome="The procedure went well.",
        follow_up=NOT_DOCUMENTED_FOLLOW_UP,
        follow_up_source_quote=None,
    )
    consolidated = ConsolidatedProcedure(summary=summary, document_ids=["doc-1"])
    request = ProcedureSummarizationRequest(
        appointment_id=uuid4(), user_id=uuid4(), async_token=async_token
    )

    await service._persist(
        request, consolidated=[consolidated], documents_analyzed=1, extraction_errors=[]
    )

    rows = service.summaries_repo.upsert_many_for_source.call_args.kwargs["rows"]
    assert rows[0]["summary_metadata"]["async_token"] == async_token
