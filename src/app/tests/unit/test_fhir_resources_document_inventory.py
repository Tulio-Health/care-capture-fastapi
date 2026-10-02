"""Regression test for round9-revision3.md S3.3 step 3 (HARD GATE, required regression test #1
of the task's required list): `document_inventory`'s shape must be computed over the
pre-exclusion row set, byte-identical in content/shape to the pre-redesign version, because it is
compared for EQUALITY downstream by `attachment_summarization.py`'s `SOURCE_MANIFEST_CHANGED`
guard. Without this, the first cache-hit path after deploy raises a retryable
`SOURCE_MANIFEST_CHANGED` on every request -- a retry storm, not a clean error.

This repo has no DB-backed test fixture anywhere (`src/app/tests/integration/` is empty;
`tests/unit/conftest.py` no-ops `setup_test_database`), so this test mocks `session.execute` to
return a canned pre-exclusion row set for the INVENTORY query (unchanged shape, S3.3 step 3) and
independently re-derives the expected `document_inventory` dict using the EXACT formula the
pre-redesign code used (quoted from `origin/develop @ bd509af` / Fix 4's pinned revision, see
`fhir_resources.py`'s own git history) -- then asserts the post-redesign repository produces an
identical dict for an identical canned row set.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository
from src.app.services.summary_outcomes import source_manifest


def _resource(ehr_resource_id, data, updated_at="2026-01-01T00:00:00Z"):
    return SimpleNamespace(ehr_resource_id=ehr_resource_id, data=data, updated_at=updated_at)


def _pre_redesign_document_inventory(inventory_rows):
    """Verbatim re-derivation of the pre-redesign formula (fhir_resources.py, pre-F3):
        resources = [resource for resource, reason in inventory if reason is None]
        excluded = [{"source_id": str(resource.ehr_resource_id), "reason": reason}
                    for resource, reason in inventory if reason is not None]
        self.document_inventory = {"total_references": len(inventory),
            "excluded_documents": len(excluded), "exclusions": excluded[:20],
            "exclusions_omitted": max(0, len(excluded) - 20),
            "manifest": source_manifest([resource for resource, reason in inventory])}
    """
    excluded = [
        {"source_id": str(resource.ehr_resource_id), "reason": reason}
        for resource, reason in inventory_rows
        if reason is not None
    ]
    return {
        "total_references": len(inventory_rows),
        "excluded_documents": len(excluded),
        "exclusions": excluded[:20],
        "exclusions_omitted": max(0, len(excluded) - 20),
        "manifest": source_manifest([resource for resource, _ in inventory_rows]),
    }


class _FakeInventoryResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSelectionResult:
    def __init__(self, resources):
        self._resources = resources

    def scalars(self):
        return SimpleNamespace(all=lambda: self._resources)


@pytest.mark.asyncio
async def test_document_inventory_byte_identical_for_a_fixed_pre_exclusion_row_set():
    # A mixed row set: one included document, one excluded (reason set, simulating a matched
    # exclude rule), one attachment-less document (still appears in the INVENTORY query, since
    # that query is unchanged and does NOT carry the new attachments predicate -- S3.3 step 3).
    inventory_rows = [
        (_resource("doc-1", {"type": "Visit Note", "date": "2026-02-03"}), None),
        (_resource("doc-2", {"type": "Billing Statement", "date": "2026-02-02"}), "document_type_rule:0"),
        (_resource("doc-3", {"type": "Consult Note", "date": "2026-02-01"}), None),
    ]
    expected = _pre_redesign_document_inventory(inventory_rows)

    repo = FhirResourcesRepository.__new__(FhirResourcesRepository)
    repo.session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeInventoryResult(inventory_rows),
                _FakeSelectionResult([inventory_rows[0][0], inventory_rows[2][0]]),
            ]
        )
    )

    await repo.get_document_references_with_attachments(
        user_id="user-1",
        encounter_id="enc-1",
        selection_profile="legacy",
        rule_snapshot=([], {"tier": "floor", "digest": "test"}),
    )

    assert repo.document_inventory == expected
    assert repo.document_inventory["total_references"] == 3
    assert repo.document_inventory["excluded_documents"] == 1
    assert repo.document_inventory["exclusions"] == [{"source_id": "doc-2", "reason": "document_type_rule:0"}]
    assert repo.document_inventory["exclusions_omitted"] == 0


@pytest.mark.asyncio
async def test_document_inventory_still_computed_when_pre_exclusion_count_exceeds_the_old_raise_threshold():
    """Before this fix, >100 pre-exclusion rows raised DOCUMENT_LIMIT_EXCEEDED before
    `document_inventory` was ever assigned -- there was no "today" value to match for this case.
    Post-fix, the raise is gone (S3.3 step 5) for every selection_profile, so document_inventory
    IS now populated even when the INVENTORY query's own 101-row limit is saturated. This proves
    the removal doesn't silently skip setting the attribute (which would break the
    SOURCE_MANIFEST_CHANGED equality check on every encounter the fix was meant to help).
    """
    inventory_rows = [
        (_resource(f"doc-{i}", {"type": "Visit Note", "date": "2026-01-01"}), None) for i in range(101)
    ]
    expected = _pre_redesign_document_inventory(inventory_rows)

    repo = FhirResourcesRepository.__new__(FhirResourcesRepository)
    repo.session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeInventoryResult(inventory_rows),
                _FakeSelectionResult([row[0] for row in inventory_rows]),
            ]
        )
    )

    await repo.get_document_references_with_attachments(
        user_id="user-1",
        encounter_id="enc-1",
        selection_profile="legacy",
        rule_snapshot=([], {"tier": "floor", "digest": "test"}),
    )

    assert repo.document_inventory == expected
    assert repo.document_inventory["total_references"] == 101
    assert repo.document_inventory["exclusions_omitted"] == 0
