"""Unit tests for the `includeForSummary` soft-preference, now subsumed into
`fhir_resources.get_document_references_with_attachments`'s SQL ORDER BY
(round9-revision3.md S3.1.2A / F4 / F4b).

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

Per-test disposition (round9-revision3.md S3.1.2A, resolves `rt2-f4b-test-migration-incoherent`):
- `test_mixed_flags_returns_full_set_with_flagged_first` (was
  `test_mixed_flags_narrows_to_only_flagged_true_documents`): REWRITTEN. The Python-side
  narrowing this test encoded is gone -- `_fetch_document_references` is now a pure passthrough
  of whatever `fhir_repo.get_document_references_with_attachments` returns, already ordered by
  SQL (preference_rank, include_for_summary_rank, date desc, ehr_resource_id). This is the ONE
  test that encoded the deleted semantics.
- The next four (`test_no_documents_flagged_true_falls_back_to_full_unfiltered_set`,
  `test_field_entirely_absent_on_every_document_falls_back_unchanged`,
  `test_all_documents_flagged_true_returns_full_set_unchanged`,
  `test_no_documents_at_all_returns_empty_list`) are KEPT VERBATIM UNCHANGED -- their assertions
  are already true under passthrough, for a structural reason now rather than a conditional one.
  Only the shared `_service`/`_FakeFhirRepo` test infrastructure below needed updating (the new
  `selection_profile`/`rule_snapshot` kwargs and the `_rule_snapshot` instance attribute), not the
  test bodies themselves.
- Three NEW tests added at the bottom: cap-filling (scoped within each preference_rank band,
  per the round-7 closing-review correction -- an unqualified "every flagged document survives
  the cap" would be false by construction), the sub-cap widening (intentional, asserted so it
  isn't mistaken for a regression), and rank-0 survival through `document_ingestion.
  process_attachments`'s own, DIFFERENT (attachment-counted, not DocumentReference-counted) cap
  (`rt2-cap-unit-mismatch-docrefs-vs-attachments`).

Testing-infra note: this repo has no DB-backed test fixture anywhere (`src/app/tests/integration/`
is empty; `tests/unit/conftest.py` no-ops `setup_test_database`), so the cap-filling and sub-cap
tests below validate the documented ORDER BY + LIMIT contract (preference_rank ASC,
include_for_summary_rank ASC, date DESC, ehr_resource_id ASC, then LIMIT) as a standalone
specification via `_order_then_cap`, a small test-only mirror of that contract -- NOT the literal
SQL in `fhir_resources.py`, which this suite cannot execute. The rank-0-survival test has no such
caveat: it drives the real, production `document_ingestion.process_attachments`.
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
        self.calls = []

    async def get_document_references_with_attachments(
        self, user_id, encounter_id, selection_profile="legacy", rule_snapshot=None
    ):
        # Signature mirrors the real repository post-F3: _fetch_document_references always
        # passes selection_profile='visit_summary_preferred' and a pinned rule_snapshot now,
        # so the fake must accept (and can record) both.
        self.calls.append({"selection_profile": selection_profile, "rule_snapshot": rule_snapshot})
        return self._doc_references


def _service(doc_references):
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    service.fhir_repo = _FakeFhirRepo(doc_references)
    service.logger = SimpleNamespace(debug=lambda *a, **k: None)
    # __new__ bypasses __init__, so the rule-snapshot pinning attribute (S3.3 step 4 / F4)
    # must be set explicitly here, same as every other instance attribute these tests rely on.
    service._rule_snapshot = ([], {"tier": "floor", "digest": "test"})
    return service


def _request():
    return AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())


def _appointment():
    return SimpleNamespace(ehr_entity_id="enc-123")


@pytest.mark.asyncio
async def test_mixed_flags_returns_full_set_with_flagged_first():
    """REWRITE (semantics change, round9-revision3.md S3.1.2A): a mix of True/False/absent no
    longer narrows to only the flagged document -- it is subsumed into SQL ordering, so ALL
    documents are returned, with the flagged one first (the fake repo already returns them in
    SQL order; the service does nothing but pass that through now)."""
    flagged = _doc("doc-true", include_for_summary=True)
    docs = [
        flagged,
        _doc("doc-false", include_for_summary=False),
        _doc("doc-absent"),
    ]
    service = _service(docs)

    result = await service._fetch_document_references(_request(), _appointment())

    assert result == docs  # (a) all three documents are returned, unnarrowed
    assert result[0] is flagged  # (b) the flagged document is first
    # And the call into the repository carries the new profile + the pinned snapshot (F4/S3.3
    # step 4), not a bare two-arg call -- the Python-side narrowing really is gone, not just the
    # assertion relaxed.
    assert service.fhir_repo.calls[-1]["selection_profile"] == "visit_summary_preferred"
    assert service.fhir_repo.calls[-1]["rule_snapshot"] == service._rule_snapshot


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


# ---------------------------------------------------------------------------
# New tests (round9-revision3.md S3.1.2A / F4b)
# ---------------------------------------------------------------------------

def _order_then_cap(docs, cap):
    """Test-only mirror of fhir_resources.py's SELECTION query ORDER BY + LIMIT contract:
    `ORDER BY preference_rank ASC, include_for_summary_rank ASC, date DESC, ehr_resource_id ASC`,
    then `LIMIT cap`. Built from stable sorts applied least-significant-key-first (Python's sort
    is stable), which is exactly how a multi-column SQL ORDER BY composes. Exists because this
    repo has no DB fixture to execute the real SQL against (see module docstring) -- this encodes
    the documented contract as an assertable, deterministic specification.

    Each `doc` is a dict: {"ehr_resource_id", "date" (ISO string), "preference_rank" (0/1),
    "include_for_summary_rank" (0/1)}.
    """
    ordered = sorted(docs, key=lambda d: d["ehr_resource_id"])
    ordered = sorted(ordered, key=lambda d: d["date"], reverse=True)
    ordered = sorted(ordered, key=lambda d: d["include_for_summary_rank"])
    ordered = sorted(ordered, key=lambda d: d["preference_rank"])
    return ordered[:cap]


def test_flagged_documents_fill_the_cap_before_unflagged():
    """resolves rt2-subsume-widens-document-set / R1b: within each preference_rank band,
    flagged (include_for_summary_rank=0) documents fill the cap before unflagged ones of the
    SAME band -- an emergent property of ORDER BY + LIMIT, asserted directly because it is
    otherwise invisible in any single function body.

    Deliberately NOT asserting "every flagged document survives the cap" (round-7 closing-review
    correction): a rank-0 UNFLAGGED document legitimately precedes a rank-1 FLAGGED one, because
    preference_rank is the leading ORDER BY key. The two rank-1 flagged docs below are dropped by
    the cap despite being flagged, which is the band-crossing counterexample that makes an
    unqualified claim false by construction.
    """
    docs = [
        {"ehr_resource_id": "r0-f1", "date": "2026-01-04", "preference_rank": 0, "include_for_summary_rank": 0},
        {"ehr_resource_id": "r0-f2", "date": "2026-01-03", "preference_rank": 0, "include_for_summary_rank": 0},
        {"ehr_resource_id": "r0-u1", "date": "2026-01-02", "preference_rank": 0, "include_for_summary_rank": 1},
        {"ehr_resource_id": "r0-u2", "date": "2026-01-01", "preference_rank": 0, "include_for_summary_rank": 1},
        {"ehr_resource_id": "r1-f1", "date": "2026-01-06", "preference_rank": 1, "include_for_summary_rank": 0},
        {"ehr_resource_id": "r1-f2", "date": "2026-01-05", "preference_rank": 1, "include_for_summary_rank": 0},
    ]

    result_ids = [d["ehr_resource_id"] for d in _order_then_cap(docs, cap=3)]

    assert result_ids == ["r0-f1", "r0-f2", "r0-u1"]
    # Cap-filling within the rank-0 band: both flagged rank-0 docs precede the one unflagged
    # rank-0 doc that also made the cap.
    assert result_ids.index("r0-f1") < result_ids.index("r0-u1")
    assert result_ids.index("r0-f2") < result_ids.index("r0-u1")
    # Band-crossing counterexample: rank-1 docs are dropped by the cap EVEN THOUGH they are
    # flagged -- "every flagged document survives the cap" is false by construction.
    assert "r1-f1" not in result_ids
    assert "r1-f2" not in result_ids


def test_sub_cap_mixed_flag_encounter_returns_every_document():
    """resolves rt2-subsume-widens-document-set / R1b: for an encounter below the cap, the
    accepted sub-cap widening is intentional -- every document is returned regardless of flag,
    which is a real behavior change from the pre-redesign hard narrowing (dilution + model cost,
    not a budget breach), asserted here so a future reader does not mistake it for a regression.
    """
    docs = [
        {"ehr_resource_id": "a", "date": "2026-01-03", "preference_rank": 0, "include_for_summary_rank": 0},
        {"ehr_resource_id": "b", "date": "2026-01-02", "preference_rank": 0, "include_for_summary_rank": 1},
        {"ehr_resource_id": "c", "date": "2026-01-01", "preference_rank": 1, "include_for_summary_rank": 1},
    ]

    result = _order_then_cap(docs, cap=10)

    assert {d["ehr_resource_id"] for d in result} == {"a", "b", "c"}
    assert len(result) == 3


@pytest.mark.asyncio
async def test_rank0_documents_survive_process_attachments_on_an_over_cap_encounter():
    """resolves rt2-cap-unit-mismatch-docrefs-vs-attachments (round9-revision3.md S3.1.2A /
    S3.3 step 2): getting rank-0 DocumentReferences to the front of the repository's result is
    necessary but not sufficient -- document_ingestion.process_attachments applies its OWN,
    DIFFERENT cap (MAX_DOCUMENTS, attachment-counted after format-dedup) further downstream. This
    asserts the ordering property survives THAT boundary too, unlike test_flagged_documents_fill_
    the_cap_before_unflagged above (which only tests the SQL-level contract): feed
    process_attachments an input list already in SQL-selection order -- every rank-0 reference
    first, rank-1 references after -- and confirm every rank-0 document is fully processed (no
    extraction_error) while the cap trips exactly at the rank-0/rank-1 boundary, letting no
    rank-1 document in ahead of a rank-0 one.
    """
    from src.app.services.document_ingestion import process_attachments, MAX_DOCUMENTS

    class _FakeStorage:
        async def download_document(self, file_path):
            return b"content"

    class _FakeExtractor:
        MAX_FILE_SIZE = 50 * 1024 * 1024

        async def extract_text_async(self, content, content_type, file_name=None):
            return f"extracted text {file_name}"

    def _ref(resource_id):
        return SimpleNamespace(
            ehr_resource_id=resource_id,
            data={
                "type": "Document",
                "date": "2026-01-01T00:00:00Z",
                "attachments": [{
                    "filePath": f"{resource_id}.html", "checksum": f"csum-{resource_id}",
                    "downloadStatus": "success", "contentType": "text/html",
                    "title": "Doc", "fileName": f"{resource_id}.html",
                }],
            },
        )

    # Already in SQL-selection order: MAX_DOCUMENTS rank-0 references first, 5 rank-1
    # references after -- exactly the shape fhir_resources.py's SELECTION query hands to
    # process_attachments under selection_profile='visit_summary_preferred'.
    rank0_refs = [_ref(f"rank0-{i}") for i in range(MAX_DOCUMENTS)]
    rank1_refs = [_ref(f"rank1-{i}") for i in range(5)]

    result = await process_attachments(rank0_refs + rank1_refs, _FakeStorage(), _FakeExtractor())

    assert len(result) == MAX_DOCUMENTS + 1  # every rank-0 doc, plus the truncation sentinel
    assert all(not doc.extraction_error for doc in result[:MAX_DOCUMENTS])
    # The sentinel's exact extraction_error CODE is F7's concern (its canonicalization is
    # covered by test_document_ingestion_dedup.py's cap test and
    # test_max_documents_sentinel_never_describes_as_internal_processing_error); this test is
    # about ordering/boundary placement, so it only asserts a sentinel is present at the cap
    # boundary, not which exact string it carries.
    assert result[MAX_DOCUMENTS].extraction_error is not None
