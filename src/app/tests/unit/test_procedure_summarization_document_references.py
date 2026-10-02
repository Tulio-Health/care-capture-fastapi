"""Regression test for round9-revision3.md S3.3 step 6 (required regression test #5 of the
task's required list): the new attachments predicate (S3.3 step 1b) narrows the repository's
result BEFORE `ProcedureSummarizationService`'s own `isProcedureDocument is True` post-filter
runs. This guards that narrowing against the post-filter: for a mixed encounter (attachment-
bearing procedure docs and attachment-bearing non-procedure docs -- simulating a result set the
new predicate has already filtered to attachment-bearing rows only), every attachment-bearing
`isProcedureDocument` document must still survive into the procedure feed.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.app.models.procedure_summarization import ProcedureSummarizationRequest
from src.app.services.summarization.procedure_summarization import (
    ProcedureSummarizationService,
)


def _doc(ehr_resource_id, is_procedure_document):
    return SimpleNamespace(
        ehr_resource_id=ehr_resource_id,
        data={
            "type": "Document",
            "date": "2026-01-01T00:00:00Z",
            "isProcedureDocument": is_procedure_document,
            "attachments": [{"downloadStatus": "success"}],
        },
    )


class _FakeFhirRepo:
    def __init__(self, doc_references):
        self._doc_references = doc_references
        self.calls = []

    async def get_document_references_with_attachments(self, **kwargs):
        # The real repository, post-F3, already applies the attachments predicate in SQL --
        # every row this fake returns is attachment-bearing, same as a real post-predicate
        # result set would be.
        self.calls.append(kwargs)
        return self._doc_references


def _service(doc_references):
    service = ProcedureSummarizationService.__new__(ProcedureSummarizationService)
    service.fhir_repo = _FakeFhirRepo(doc_references)
    service.logger = SimpleNamespace(debug=lambda *a, **k: None)
    return service


def _appointment():
    return SimpleNamespace(ehr_entity_id="enc-mixed")


@pytest.mark.asyncio
async def test_every_attachment_bearing_procedure_document_survives_for_a_mixed_encounter():
    procedure_doc_1 = _doc("proc-1", is_procedure_document=True)
    procedure_doc_2 = _doc("proc-2", is_procedure_document=True)
    non_procedure_doc = _doc("note-1", is_procedure_document=False)
    docs = [procedure_doc_1, non_procedure_doc, procedure_doc_2]

    user_id = uuid4()
    request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=user_id)
    service = _service(docs)

    result = await service._fetch_procedure_document_references(request, _appointment())

    assert result == [procedure_doc_1, procedure_doc_2]


@pytest.mark.asyncio
async def test_procedure_caller_uses_legacy_default_profile_with_no_new_kwargs():
    """F5 (round9-revision3.md): procedure/comprehensive callers keep the LEGACY call signature
    unchanged -- they must not pass selection_profile or rule_snapshot at all. The repository
    defaults selection_profile='legacy' / rule_snapshot=None for exactly this reason, so neither
    caller needed a single line of change."""
    docs = [_doc("proc-1", is_procedure_document=True)]
    user_id = uuid4()
    request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=user_id)
    service = _service(docs)

    await service._fetch_procedure_document_references(request, _appointment())

    assert service.fhir_repo.calls == [{"user_id": str(user_id), "encounter_id": "enc-mixed"}]
