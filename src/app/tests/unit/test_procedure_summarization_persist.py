"""Unit tests for the new one-row-per-(consolidated)-procedure persistence behavior
(Task 3): `ConversationSummariesRepository.upsert_many_for_source`'s upsert-then-prune logic,
which `ProcedureSummarizationService._persist` delegates to.

Uses a lightweight fake AsyncSession (no real DB/engine) so these stay true unit tests -
`ConversationSummaries` is a plain SQLAlchemy declarative object and can be constructed
directly without a DB connection as long as nothing actually executes SQL against it.
"""

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


class _FakeSession:
    """Stands in for AsyncSession: `execute()` always returns the `existing_rows` fixture
    passed at construction (mirrors `get_all_by_appointment_id_and_source`'s single query),
    `add`/`delete` just record what was called, `commit`/`refresh` are no-ops."""

    def __init__(self, existing_rows):
        self.existing_rows = existing_rows
        self.added = []
        self.deleted = []
        self.committed = False

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

    async def refresh(self, _obj):
        pass


def _row_data(
    document_ids: list[str], summary_text: str = "Cardiac catheterization"
) -> dict:
    user_id = uuid4()
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


def _existing_row(document_ids: list[str]) -> ConversationSummaries:
    return ConversationSummaries(
        id=uuid4(),
        appointment_id=uuid4(),
        user_id=uuid4(),
        summary_text="old text",
        summary_metadata={
            "source": "procedure_summary",
            "source_document_ids": sorted(document_ids),
        },
        created_by=uuid4(),
        updated_by=uuid4(),
    )


async def test_n_procedures_creates_n_rows_with_correct_keys():
    appointment_id = uuid4()
    session = _FakeSession(existing_rows=[])
    repo = ConversationSummariesRepository(session)

    rows = [_row_data(["doc-1"]), _row_data(["doc-2"]), _row_data(["doc-3a", "doc-3b"])]

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
    existing_a = _existing_row(["doc-1"])
    existing_b = _existing_row(["doc-2"])
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    # Only doc-1's procedure survives this sync (doc-2 was reclassified/removed).
    rows = [_row_data(["doc-1"], summary_text="updated text")]

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows
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
    existing_a = _existing_row(["doc-1"])
    existing_b = _existing_row(["doc-2"])
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    rows = [_row_data(["doc-1", "doc-2"])]  # now one merged row covering both documents

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows
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


async def test_zero_procedures_deletes_all_existing_rows_and_creates_nothing():
    appointment_id = uuid4()
    existing_a = _existing_row(["doc-1"])
    existing_b = _existing_row(["doc-2"])
    session = _FakeSession(existing_rows=[existing_a, existing_b])
    repo = ConversationSummariesRepository(session)

    result = await repo.upsert_many_for_source(
        appointment_id, "procedure_summary", rows=[]
    )

    assert result == []
    assert len(session.added) == 0
    assert sorted(session.deleted, key=id) == sorted([existing_a, existing_b], key=id)
    assert session.committed
