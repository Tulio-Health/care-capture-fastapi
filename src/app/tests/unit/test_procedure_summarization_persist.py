"""Unit tests for the new one-row-per-(consolidated)-procedure persistence behavior
(Task 3): `ConversationSummariesRepository.upsert_many_for_source`'s upsert-then-prune logic,
which `ProcedureSummarizationService._persist` delegates to.

Uses a lightweight fake AsyncSession (no real DB/engine) so these stay true unit tests -
`ConversationSummaries` is a plain SQLAlchemy declarative object and can be constructed
directly without a DB connection as long as nothing actually executes SQL against it.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.app.chains.procedure_extraction.consolidation import ConsolidatedProcedure
from src.app.db.objects.entities.conversation_summaries import ConversationSummaries
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummarizationRequest,
    ProcedureSummary,
)
from src.app.services.summarization.procedure_summarization import ProcedureSummarizationService

pytestmark = pytest.mark.asyncio


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        # Stands in for the `Appointment.id` ownership-check query `appointment_belongs_to`
        # runs inside `_lock_scope`, and for the advisory-lock select - neither is what these
        # persistence tests exercise (ownership itself is covered by
        # test_conversation_summaries_repo_safety.py::TestAppointmentBelongsTo), so this fake
        # always reports "found" regardless of which query it backs.
        return True


class _FakeSession:
    """Stands in for AsyncSession: `execute()` always returns the `existing_rows` fixture
    passed at construction (mirrors `get_all_by_appointment_id_and_source`'s single query),
    `add`/`delete` just record what was called, `commit`/`rollback`/`flush` are no-ops, and
    `refresh` fills in the server-side-default columns (`id`, `created_at`, `updated_at`) a
    real Postgres round-trip would populate - `_commit_validated` calls `refresh` then
    validates every touched row against the `ConversationSummary` pydantic model, which
    requires all four."""

    def __init__(self, existing_rows):
        self.existing_rows = existing_rows
        self.added = []
        self.deleted = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, _stmt):
        return _FakeResult(self.existing_rows)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)
        if obj in self.existing_rows:
            self.existing_rows.remove(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def flush(self):
        pass

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        now = datetime.now(timezone.utc)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now


def _row_data(
    document_ids: list[str],
    user_id,
    summary_text: str = "Cardiac catheterization",
) -> dict:
    """`user_id` is a required, explicit param (not a fresh uuid4() per call) so every row in
    a multi-row `rows` list - and every existing row it's compared against - shares the SAME
    owner. `upsert_many_for_source` derives `owner_id` from `rows[0]["user_id"]` and raises
    SUMMARY_SCOPE_MISMATCH the moment any row (new or existing) disagrees with it - a fixture
    that stamps a random user_id per row trips that check for the wrong reason."""
    return {
        "user_id": user_id,
        "created_by": user_id,
        "updated_by": user_id,
        "summary_text": summary_text,
        "data": {
            "reason": "reason",
            "procedure_details": "details",
            "outcome": "outcome",
            "follow_up": "follow up",
        },
        "key_points": None,
        "medications": None,
        "diagnoses": None,
        "instructions": None,
        "recommendations": None,
        "summary_metadata": {
            "source": "procedure_summary",
            "summaryType": "procedure",
            "source_document_ids": sorted(document_ids),
        },
    }


def _existing_row(
    document_ids: list[str], user_id, validation_status: str = "passed"
) -> ConversationSummaries:
    """`user_id` is required for the same reason as `_row_data`'s. `validation_status` defaults
    to "passed" to match what `_persist` actually stamps on every real procedure_summary row
    (procedure_summarization.py's summary_metadata dict) - the not-allow_prune preservation
    branch in `upsert_many_for_source` only marks/notices rows whose metadata already says
    "passed"."""
    now = datetime.now(timezone.utc)
    return ConversationSummaries(
        id=uuid4(),
        appointment_id=uuid4(),
        user_id=user_id,
        summary_text="old text",
        summary_metadata={
            "source": "procedure_summary",
            "source_document_ids": sorted(document_ids),
            "validation_status": validation_status,
        },
        created_by=uuid4(),
        updated_by=uuid4(),
        created_at=now,
        updated_at=now,
    )


async def test_n_procedures_creates_n_rows_with_correct_keys():
    appointment_id = uuid4()
    user_id = uuid4()
    session = _FakeSession(existing_rows=[])
    repo = ConversationSummariesRepository(session)

    rows = [
        _row_data(["doc-1"], user_id),
        _row_data(["doc-2"], user_id),
        _row_data(["doc-3a", "doc-3b"], user_id),
    ]

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows
    )

    assert len(result) == 3
    assert len(session.added) == 3
    assert session.committed
    keys = {",".join(sorted(r.summary_metadata["source_document_ids"])) for r in result}
    assert keys == {"doc-1", "doc-2", "doc-3a,doc-3b"}


async def test_resync_with_fewer_procedures_prunes_stale_row():
    appointment_id = uuid4()
    user_id = uuid4()
    existing_a = _existing_row(["doc-1"], user_id)
    existing_b = _existing_row(["doc-2"], user_id)
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    # Only doc-1's procedure survives this sync (doc-2 was reclassified/removed).
    rows = [_row_data(["doc-1"], user_id, summary_text="updated text")]

    # PR-3's persistence rewrite requires allow_prune=True explicitly - without it, an
    # unmatched existing row is kept-with-notice rather than deleted (see the A01 tests below).
    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows, allow_prune=True
    )

    assert len(result) == 1
    assert result[0] is existing_a  # updated in place, not recreated
    assert result[0].summary_text == "updated text"
    assert session.deleted == [existing_b]
    assert len(session.added) == 0


async def test_consolidation_prunes_the_now_redundant_second_row():
    """Two previously-separate rows (doc-1, doc-2) get consolidated into one merged row on
    this sync - the second row must be pruned, not left behind as a duplicate."""
    appointment_id = uuid4()
    user_id = uuid4()
    existing_a = _existing_row(["doc-1"], user_id)
    existing_b = _existing_row(["doc-2"], user_id)
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    rows = [_row_data(["doc-1", "doc-2"], user_id)]  # now one merged row covering both documents

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows, allow_prune=True
    )

    assert len(result) == 1
    assert sorted(result[0].summary_metadata["source_document_ids"]) == [
        "doc-1",
        "doc-2",
    ]
    assert sorted(session.deleted, key=id) == sorted([existing_a, existing_b], key=id)
    assert len(session.added) == 1  # neither existing row's key matched -> a fresh row


async def test_persist_includes_procedure_type_as_its_own_data_key():
    """`_persist`'s row-building must surface `procedure_type` in `data` (translatable content,
    same as reason/procedure_details/outcome/follow_up) alongside - not instead of - the rest."""
    service = ProcedureSummarizationService.__new__(ProcedureSummarizationService)
    service.logger = MagicMock()
    service.summaries_repo = MagicMock()
    service.summaries_repo.upsert_many_for_source = AsyncMock(return_value=[])

    summary = ProcedureSummary(
        source_document_title="Procedure Note",
        event_source_quote="Cardiac catheterization with coronary angioplasty performed 2026-06-29",
        procedure_type="Cardiac catheterization with coronary angioplasty",
        procedure_date="2026-06-29",
        performed_by=["Dr. A"],
        reason="You had chest pain.",
        procedure_details="A catheter was inserted through your wrist to check your arteries.",
        outcome="The procedure went well with no complications.",
        follow_up=NOT_DOCUMENTED_FOLLOW_UP,
        follow_up_source_quote=None,
    )
    consolidated = ConsolidatedProcedure(summary=summary, document_ids=["doc-1"])
    request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())

    await service._persist(
        request, consolidated=[consolidated], documents_analyzed=1, extraction_errors=[]
    )

    rows = service.summaries_repo.upsert_many_for_source.call_args.kwargs["rows"]
    assert rows[0]["data"]["procedure_type"] == "Cardiac catheterization with coronary angioplasty"
    assert rows[0]["data"]["reason"] == "You had chest pain."
    assert rows[0]["summary_text"] == "A catheter was inserted through your wrist to check your arteries."


# --- A01 data-loss guard: an empty `rows` list ("authoritative zero procedures found" OR
# "batch failed before producing anything") must NEVER unconditionally wipe existing rows.
# These three tests map the three real branches of `upsert_many_for_source`'s current
# (correct) behavior; they replace a prior test that encoded the pre-fix
# unconditional-deletion behavior as "correct" - see the negative-control check in this PR's
# commit message/notes for proof these three actually catch that regression if it returns.


async def test_empty_rows_default_call_preserves_existing_rows_without_allow_prune():
    """(a) The default call (no allow_prune) on empty input is a no-op for deletion purposes -
    existing rows are preserved, never wiped, even though nothing new was written."""
    appointment_id = uuid4()
    user_id = uuid4()
    existing_a = _existing_row(["doc-1"], user_id)
    existing_b = _existing_row(["doc-2"], user_id)
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    await repo.upsert_many_for_source(appointment_id, "procedure_summary", rows=[])

    assert session.deleted == []
    assert existing_a in session.existing_rows
    assert existing_b in session.existing_rows


async def test_empty_rows_allow_prune_without_owner_is_refused():
    """(b) allow_prune=True on empty input with no owner established (no rows to infer one
    from, and no explicit user_id) is refused outright rather than deleting anything."""
    appointment_id = uuid4()
    session = _FakeSession(existing_rows=[])
    repo = ConversationSummariesRepository(session)

    with pytest.raises(ValueError, match="EMPTY_REPLACEMENT_REQUIRES_OWNER"):
        await repo.upsert_many_for_source(
            appointment_id, "procedure_summary", rows=[], allow_prune=True
        )


async def test_empty_rows_allow_prune_with_explicit_owner_deletes_all_existing_rows():
    """(c) The one sanctioned case: allow_prune=True WITH an explicit owner (the real
    "authoritative extraction found zero procedures for this user" signal from
    ProcedureSummarizationService._persist) actually deletes the existing rows."""
    appointment_id = uuid4()
    user_id = uuid4()
    existing_a = _existing_row(["doc-1"], user_id)
    existing_b = _existing_row(["doc-2"], user_id)
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows=[], allow_prune=True, user_id=user_id
    )

    assert result == []
    assert len(session.added) == 0
    assert sorted(session.deleted, key=id) == sorted([existing_a, existing_b], key=id)
    assert session.committed


async def test_empty_rows_preservation_notice_uses_the_correct_apostrophe():
    """(d) The preservation-with-notice path (default call, existing rows with
    validation_status="passed" - the status every real procedure_summary row is stamped with,
    see procedure_summarization.py's summary_metadata dict) prepends a user-facing notice using
    a typographic apostrophe (U+2019), not a plain ASCII apostrophe - match it exactly."""
    appointment_id = uuid4()
    user_id = uuid4()
    existing_a = _existing_row(["doc-1"], user_id)
    session = _FakeSession(existing_rows=[existing_a])
    repo = ConversationSummariesRepository(session)

    await repo.upsert_many_for_source(appointment_id, "procedure_summary", rows=[])

    notice = "We couldn\u2019t update this summary. The previous summary is shown below.\n\n"
    assert existing_a.summary_text == notice + "old text"
    assert existing_a.summary_metadata["last_refresh_outcome"] == {
        "processing_outcome": "partial"
    }
