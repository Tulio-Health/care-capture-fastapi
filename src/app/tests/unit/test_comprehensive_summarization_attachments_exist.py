"""Regression tests for round9-revision3.md S3.3 step 6 (required regression tests #3 and #4 of
the task's required list): `ComprehensiveSummarizationService._check_attachments_exist`'s two
independent behavior changes from the F3 redesign.

Test #3 covers the raise removal (S3.3 step 5): before the fix, `get_document_references_with_
attachments` raised `DOCUMENT_LIMIT_EXCEEDED` for any encounter with >100 qualifying
DocumentReferences, which `_check_attachments_exist` converted into
`raise RuntimeError("DOCUMENT_INVENTORY_UNAVAILABLE")`, silently routing comprehensive's over-cap
encounters to `_run_attachment_with_fhir_fallback`. Post-fix, order-then-cap means no raise ever
fires for this reason -- this is an intended routing change (S3.3 step 6's decision table), not a
side effect, and is asserted here.

Test #4 covers the NEW attachments predicate (S3.3 step 1b) in the opposite direction, for a
different input class (not to be conflated with test #3): an encounter whose only
DocumentReferences have no attachments now correctly returns `False` (previously `True`, since
the predicate didn't exist and `len(doc_refs) > 0` only checked row existence, not attachment
existence), routing that encounter to `_run_attachment_with_fhir_fallback` instead of the
attachment path finding nothing to read.

This repo has no DB-backed test fixture (see `test_fhir_resources_document_inventory.py`'s module
docstring for the full explanation), so both tests mock `FhirResourcesRepository` at its
`comprehensive_summarization` import site and drive `_check_attachments_exist` directly -- they
exercise the CALLER's handling of the repository's new return shape, which is what S3.3 step 6
actually decided; the repository's own SQL is covered separately by
`test_fhir_resources_document_inventory.py` and `_build_exclude_predicates`/
`_build_prefer_predicates`'s own unit tests.
"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.app.models.comprehensive_summarization import ComprehensiveSummarizationRequest
from src.app.services.summarization.comprehensive_summarization import (
    ComprehensiveSummarizationService,
)


class _FakeSession:
    def __init__(self, appointment):
        self._appointment = appointment

    async def execute(self, stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: self._appointment)


class _FakeSessionFactory:
    """Mimics `get_session_factory()`'s callable-returns-async-context-manager shape."""

    def __init__(self, appointment):
        self._appointment = appointment

    def __call__(self):
        return self

    async def __aenter__(self):
        return _FakeSession(self._appointment)

    async def __aexit__(self, *exc_info):
        return False


def _service(appointment):
    service = ComprehensiveSummarizationService.__new__(ComprehensiveSummarizationService)
    service.session_factory = _FakeSessionFactory(appointment)
    service.logger = SimpleNamespace(error=lambda *a, **k: None)
    return service


def _request():
    return ComprehensiveSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())


@pytest.mark.asyncio
async def test_check_attachments_exist_returns_true_for_an_over_cap_encounter():
    """resolves the S3.3 step 6 raise-removal row: >100 qualifying DocumentReferences no longer
    raises DOCUMENT_INVENTORY_UNAVAILABLE -- the caller sees a normal, large, non-empty result."""
    appointment = SimpleNamespace(ehr_entity_id="enc-over-cap", user_id=uuid4())
    over_cap_docs = [SimpleNamespace(ehr_resource_id=f"doc-{i}") for i in range(150)]

    class _FakeFhirRepo:
        def __init__(self, session):
            pass

        async def get_document_references_with_attachments(self, **kwargs):
            return over_cap_docs

    service = _service(appointment)

    with patch(
        "src.app.services.summarization.comprehensive_summarization.FhirResourcesRepository",
        _FakeFhirRepo,
    ):
        result = await service._check_attachments_exist(_request())

    assert result is True


@pytest.mark.asyncio
async def test_check_attachments_exist_returns_false_when_no_qualifying_documents_have_attachments():
    """resolves rt2-attachments-predicate-caller-impact (S3.3 step 6, new decision row): an
    encounter whose only DocumentReferences lack attachments now correctly returns False (the
    predicate filters them out of the repository's result), so the caller routes to
    _run_attachment_with_fhir_fallback instead of the attachment path finding nothing to read."""
    appointment = SimpleNamespace(ehr_entity_id="enc-no-attachments", user_id=uuid4())

    class _FakeFhirRepo:
        def __init__(self, session):
            pass

        async def get_document_references_with_attachments(self, **kwargs):
            # Simulates the new attachments predicate filtering every row out at the repository.
            return []

    service = _service(appointment)

    with patch(
        "src.app.services.summarization.comprehensive_summarization.FhirResourcesRepository",
        _FakeFhirRepo,
    ):
        result = await service._check_attachments_exist(_request())

    assert result is False
