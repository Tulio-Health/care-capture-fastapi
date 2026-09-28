"""Unit tests for the `includeForSummary` soft-preference in
`AttachmentSummarizationService._fetch_document_references`.

Real production data (see `care-capture-nodeapi` debug report
`2026-09-17-document-scope-question/document-scope-research.md`) shows `includeForSummary`
is an AI classifier flag set by care-capture-fastapi's own `/care-capture/document-type-inference`
endpoint and persisted by care-capture-emr-connector onto `DocumentReference.data`. It is
`True` only for clinically substantive documents (visit/progress/consult/discharge notes,
lab/imaging/pathology/operative reports) and `False` for administrative/non-clinical ones.
Crucially, it is only populated for the ambiguous/procedure-adjacent subset of documents that
reach the AI classifier at all -- most documents never get a value, so this MUST be a soft
preference (prefer flagged-true when present) and never a hard filter (~15% of visits have
no flagged document at all -- telephone/imaging-only encounters).

These tests guard: (1) flagged-true docs narrow the set when at least one exists, (2) the full
set is returned unchanged when nothing is flagged true (the load-bearing fallback), (3) the
same fallback holds when the field is entirely absent (never-classified connections/vendors).
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)
from src.app.models.attachment_summarization import AttachmentSummarizationRequest


def _doc(ehr_resource_id, include_for_summary=None):
    data = {"type": "Document", "date": "2026-01-01T00:00:00Z"}
    if include_for_summary is not None:
        data["includeForSummary"] = include_for_summary
    return SimpleNamespace(ehr_resource_id=ehr_resource_id, data=data)


class _FakeFhirRepo:
    def __init__(self, doc_references):
        self._doc_references = doc_references

    async def get_document_references_with_attachments(self, user_id, encounter_id):
        return self._doc_references


def _service(doc_references):
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.fhir_repo = _FakeFhirRepo(doc_references)
    service.logger = SimpleNamespace(debug=lambda *a, **k: None)
    return service


def _request():
    return AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())


def _appointment():
    return SimpleNamespace(ehr_entity_id="enc-123")


@pytest.mark.asyncio
async def test_mixed_flags_narrows_to_only_flagged_true_documents():
    """Case 1: a mix of True/False/absent -> only the True-flagged docs are returned."""
    flagged = _doc("doc-true", include_for_summary=True)
    docs = [
        flagged,
        _doc("doc-false", include_for_summary=False),
        _doc("doc-absent"),
    ]
    service = _service(docs)

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == [flagged]


@pytest.mark.asyncio
async def test_no_documents_flagged_true_falls_back_to_full_unfiltered_set():
    """Case 2 (load-bearing): every doc is False or absent -> soft preference finds nothing to
    prefer, so the ENTIRE unfiltered set is returned unchanged -- never a hard restrict that
    leaves the visit with zero documents."""
    docs = [
        _doc("doc-false-1", include_for_summary=False),
        _doc("doc-false-2", include_for_summary=False),
        _doc("doc-absent"),
    ]
    service = _service(docs)

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == docs


@pytest.mark.asyncio
async def test_field_entirely_absent_on_every_document_falls_back_unchanged():
    """Case 3: simulates a connection/vendor whose documents were never classified at all
    (field missing everywhere, not merely False) -- same fallback as case 2."""
    docs = [_doc("doc-1"), _doc("doc-2"), _doc("doc-3")]
    service = _service(docs)

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == docs


@pytest.mark.asyncio
async def test_all_documents_flagged_true_returns_full_set_unchanged():
    """Every document already flagged true -> narrowing is a no-op, full set returned."""
    docs = [
        _doc("doc-1", include_for_summary=True),
        _doc("doc-2", include_for_summary=True),
    ]
    service = _service(docs)

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == docs


@pytest.mark.asyncio
async def test_no_documents_at_all_returns_empty_list():
    """Zero DocumentReferences for the encounter -> partition logic is a no-op, empty list."""
    service = _service([])

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == []
