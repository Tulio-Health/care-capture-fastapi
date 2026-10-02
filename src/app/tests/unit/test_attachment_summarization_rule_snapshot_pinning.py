"""Regression test for round9-revision3.md S3.3 step 4 / risk R7b (required regression test #2
of the task's required list).

`get_document_references_with_attachments` re-runs `rules_client.resolve_rules()` on every call.
Before this fix, `attachment_summarization.py` called `_fetch_document_references` up to three
times per summarization attempt (the initial fetch at the top, plus a manifest re-check after a
cache hit OR after AI analysis succeeds) -- each one re-resolving rules independently. Once
`preference_rank` governs document ORDER (not just exclusion), a `live <-> stale <-> floor` tier
flip between those calls changes the ordered/selected document set, which changes the manifest
hash, which raises a retryable `SOURCE_MANIFEST_CHANGED` -- a spurious-retry generator, not a
theoretical risk (the stale-rules channel served stale for an entire historical stress run per
S3.8).

The fix: resolve the rule snapshot ONCE at the top of `analyze_attachments` and thread the SAME
snapshot into every `_fetch_document_references` call in that attempt. This test proves it by
forcing `resolve_rules()` to return a DIFFERENT rule set on every call (simulating a tier flip)
and asserting it is only ever actually called once -- and that both `_fetch_document_references`
calls (initial fetch + the cache-hit manifest re-check) used that same single resolved snapshot.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)


class _FakeFhirRepo:
    def __init__(self, docs):
        self._docs = docs
        self.calls = []
        self.eligibility_provenance = None
        self.document_inventory = None

    async def get_document_references_with_attachments(
        self, user_id, encounter_id, selection_profile="legacy", rule_snapshot=None
    ):
        self.calls.append(rule_snapshot)
        return self._docs


@pytest.mark.asyncio
async def test_rule_snapshot_resolved_once_and_reused_across_manifest_recheck():
    doc = SimpleNamespace(
        ehr_resource_id="doc-1",
        data={"type": "Document", "date": "2026-01-01T00:00:00Z"},
        updated_at="2026-01-01",
    )

    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.db = SimpleNamespace(rollback=AsyncMock())
    service.fhir_repo = _FakeFhirRepo([doc])
    service.summaries_repo = SimpleNamespace()  # unused directly -- verified_attachment_cache is mocked wholesale below
    service.s3_client = SimpleNamespace(validate_download_versions=AsyncMock())
    service.logger = SimpleNamespace(
        info=lambda *a, **k: None, debug=lambda *a, **k: None,
        warning=lambda *a, **k: None, error=lambda *a, **k: None,
    )
    service._rule_snapshot = None

    appointment = SimpleNamespace(
        ehr_entity_id="enc-123", appointment_date=None, provider_id=None, purpose=None,
    )
    service._fetch_appointment_details = AsyncMock(return_value=(appointment, "Dr. Test"))
    # extracted_documents only needs to be non-empty/truthy to pass the two early-return guards
    # before the cache check; its content is irrelevant since attachment_fingerprint/the cache
    # lookup are both mocked wholesale below.
    service._process_attachments = AsyncMock(return_value=[SimpleNamespace(extraction_error=None)])

    request = AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())

    # Simulate a tier flip: successive resolve_rules() calls return DIFFERENT rule sets --
    # exactly what the stale-rules channel does mid-request when it flaps.
    tier_sequence = [
        (["rule-v1"], {"tier": "live", "digest": "v1"}),
        (["rule-v2"], {"tier": "stale", "digest": "v2"}),
    ]
    mock_client = SimpleNamespace(resolve_rules=AsyncMock(side_effect=tier_sequence))

    with patch(
        "src.app.services.summarization.attachment_summarization.get_document_type_rules_client",
        return_value=mock_client,
    ), patch(
        "src.app.services.summary_cache.attachment_fingerprint", return_value="fp-1"
    ), patch(
        "src.app.services.summary_cache.verified_attachment_cache",
        new=AsyncMock(return_value="CACHED_SUMMARY"),
    ):
        result = await service.analyze_attachments(request)

    assert result == "CACHED_SUMMARY"
    # resolve_rules() was called exactly ONCE for the whole attempt, not once per fetch -- this
    # is what makes a mid-attempt tier flip structurally impossible to observe.
    assert mock_client.resolve_rules.await_count == 1
    # Both _fetch_document_references calls (initial fetch + the cache-hit manifest re-check)
    # used the exact SAME resolved snapshot, not two different ones from the simulated flip.
    assert len(service.fhir_repo.calls) == 2
    assert service.fhir_repo.calls[0] == tier_sequence[0]
    assert service.fhir_repo.calls[1] == tier_sequence[0]
    assert service.fhir_repo.calls[0] == service.fhir_repo.calls[1]
