"""T7a-e -- persistence of the `no_visit_summary_documents` outcome (visit-summary allowlist v2).

Rules under test (`ConversationSummariesRepository.upsert`):

* the new state NEVER overwrites an existing clinical row unless `regeneration_forced` (path 1:
  rollback, nothing written, row byte-unchanged);
* "clinical" = validated complete/partial, plus -- FLAG ON ONLY -- a legacy row (no
  `processing_outcome`, source attachment_summary, successful_documents > 0);
* forced regeneration / a non-clinical previous row: the new state replaces it, with its own
  metadata (no stale clinical keys);
* flag OFF: behaviour is exactly the parent commit's (T7e).
"""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.app.db.objects.repositories import conversation_summaries as cs_mod
from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from src.app.services.summary_outcomes import MESSAGES

NEW = "no_visit_summary_documents"
NOTICE = "We couldn’t update this summary. The previous summary is shown below.\n\n"
USER = uuid4()


class Row:
    """Mutable stand-in for the ORM entity (setattr/hasattr like the real one)."""

    def __init__(self, summary_text, summary_metadata):
        self.id = uuid4()
        self.user_id = USER
        self.summary_text = summary_text
        self.summary_metadata = summary_metadata
        self.key_points = ["kp"]
        self.medications = [{"name": "m"}]
        self.diagnoses = []
        self.instructions = []
        self.recommendations = []
        self.data = {"procedures_mentioned": ["p"]}
        self.updated_by = USER


def _clinical_meta(**extra):
    return {
        "source": "attachment_summary", "attempt_started_at": "2026-01-01T00:00:00+00:00",
        "processing_outcome": "complete", "validation_status": "passed", "is_clinical_summary": True,
        "source_fingerprint": "old-fp", "successful_documents": 2, "documents_with_accepted_content": 2, **extra,
    }


def _legacy_meta(successful=3):
    return {"source": "attachment_summary", "successful_documents": successful, "total_documents": successful}


def _incoming(outcome=NEW, *, forced=None, text=None, **extra):
    meta = {
        "source": "attachment_summary", "attempt_started_at": "2026-02-01T00:00:00+00:00", "processing_outcome": outcome,
        "validation_status": "not_applicable", "is_clinical_summary": False, "async_token": "t",
        "total_documents": 0, "successful_documents": 0, "document_metadata": [], **extra,
    }
    if forced is not None:
        meta["regeneration_forced"] = forced
    return {
        "summary_text": text or MESSAGES.get(outcome, "x"), "user_id": USER, "created_by": USER, "updated_by": USER,
        "key_points": [], "medications": [], "diagnoses": [], "instructions": [], "recommendations": [], "data": {},
        "summary_metadata": meta,
    }


@pytest.fixture
def make_repo(monkeypatch):
    def _make(previous_row, *, flag):
        monkeypatch.setattr(cs_mod, "get_settings", lambda: SimpleNamespace(VISIT_SUMMARY_ALLOWLIST_ENABLED=flag))
        session = MagicMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        repo = ConversationSummariesRepository(session)
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_by_appointment_id_and_source", AsyncMock(return_value=previous_row))
        monkeypatch.setattr(repo, "_commit_validated", AsyncMock())
        return repo

    return _make


def _snapshot(row):
    return copy.deepcopy(vars(row))


# ---------------------------------------------------------------------------------------------
# T7a: new state vs existing clinical row (not forced) -> nothing written
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "partial"])
async def test_t7a_new_state_never_overwrites_a_clinical_row(make_repo, caplog, outcome):
    row = Row("real clinical summary", _clinical_meta(processing_outcome=outcome))
    before = _snapshot(row)
    repo = make_repo(row, flag=True)
    with caplog.at_level("INFO"):
        result = await repo.upsert(uuid4(), _incoming(forced=False))
    assert result is row and _snapshot(row) == before  # byte-unchanged
    repo.session.rollback.assert_awaited_once()
    repo._commit_validated.assert_not_awaited()
    assert "allowlist_preserved_existing_summary" in caplog.text


@pytest.mark.asyncio
async def test_t7a_missing_regeneration_forced_key_counts_as_not_forced(make_repo):
    row = Row("real", _clinical_meta())
    before = _snapshot(row)
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming(forced=None))
    assert _snapshot(row) == before


# ---------------------------------------------------------------------------------------------
# T7b: legacy rows are protected when the flag is ON
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t7b_flag_on_legacy_success_row_is_preserved_from_the_new_state(make_repo):
    row = Row("legacy summary", _legacy_meta(3))
    before = _snapshot(row)
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming(forced=False))
    assert _snapshot(row) == before
    repo._commit_validated.assert_not_awaited()


@pytest.mark.asyncio
async def test_t7b_flag_on_legacy_success_row_is_preserved_from_unavailable_with_notice(make_repo):
    row = Row("legacy summary", _legacy_meta(3))
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming("unavailable"))
    assert row.summary_text == NOTICE + "legacy summary"
    assert row.summary_metadata["last_refresh_outcome"]["processing_outcome"] == "unavailable"
    assert row.summary_metadata["successful_documents"] == 3
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "meta",
    [
        {"source": "attachment_summary", "successful_documents": 0},  # legacy failure
        {"source": "attachment_summary"},  # no counts
        {"source": "attachment_summary", "successful_documents": None},
        {"source": "attachment_summary", "successful_documents": True},  # bool is not a count
        {"source": "other", "successful_documents": 5},
    ],
)
async def test_t7b_non_success_legacy_shapes_are_replaceable(make_repo, meta):
    row = Row("legacy failure", dict(meta))
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming(forced=False))
    assert row.summary_text == MESSAGES[NEW] and row.summary_metadata["processing_outcome"] == NEW
    repo._commit_validated.assert_awaited_once()


# ---------------------------------------------------------------------------------------------
# T7c: forced regeneration replaces a clinical row
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [_clinical_meta(), _legacy_meta(3)], ids=["clinical", "legacy"])
async def test_t7c_regeneration_forced_replaces_with_standalone_metadata(make_repo, previous):
    row = Row("old clinical text", dict(previous))
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming(forced=True))
    assert row.summary_text == MESSAGES[NEW]
    assert row.key_points == [] and row.medications == [] and row.data == {}
    meta = row.summary_metadata
    assert meta["processing_outcome"] == NEW and meta["regeneration_forced"] is True and meta["is_clinical_summary"] is False
    # no clinical keys leaked from the replaced summary
    for stale in ("source_fingerprint", "documents_with_accepted_content", "last_refresh_outcome"):
        assert stale not in meta
    assert meta["successful_documents"] == 0
    repo._commit_validated.assert_awaited_once()


# ---------------------------------------------------------------------------------------------
# T7d: non-clinical previous rows are replaced normally
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("previous_outcome", ["no_documents", "unavailable", NEW])
async def test_t7d_non_clinical_previous_is_replaced(make_repo, previous_outcome):
    row = Row("placeholder", {"source": "attachment_summary", "attempt_started_at": "2026-01-01T00:00:00+00:00",
                              "processing_outcome": previous_outcome, "validation_status": "not_applicable",
                              "regeneration_forced": True, "visit_summary_selection": {"old": 1}})
    repo = make_repo(row, flag=True)
    await repo.upsert(uuid4(), _incoming(forced=False, visit_summary_selection={"allowlist_version": "v2"}))
    assert row.summary_text == MESSAGES[NEW]
    assert row.summary_metadata["regeneration_forced"] is False
    assert row.summary_metadata["visit_summary_selection"] == {"allowlist_version": "v2"}
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
async def test_t7d_stale_allowlist_keys_do_not_outlive_their_row(make_repo):
    row = Row("placeholder", {"source": "attachment_summary", "attempt_started_at": "2026-01-01T00:00:00+00:00",
                              "processing_outcome": NEW, "regeneration_forced": True, "visit_summary_selection": {"x": 1}})
    repo = make_repo(row, flag=True)
    complete = _incoming("complete")
    complete["summary_metadata"].update(validation_status="passed", is_clinical_summary=True)
    await repo.upsert(uuid4(), complete)
    assert "regeneration_forced" not in row.summary_metadata and "visit_summary_selection" not in row.summary_metadata
    assert row.summary_metadata["processing_outcome"] == "complete"


@pytest.mark.asyncio
async def test_t7d_no_previous_row_creates_one(make_repo, monkeypatch):
    repo = make_repo(None, flag=True)
    created = []
    monkeypatch.setattr(cs_mod, "ConversationSummaries", lambda **kw: created.append(kw) or SimpleNamespace(**kw))
    await repo.upsert(uuid4(), _incoming(forced=False))
    assert created and created[0]["summary_metadata"]["processing_outcome"] == NEW
    repo.session.add.assert_called_once()


# ---------------------------------------------------------------------------------------------
# T7e: flag OFF == parent behaviour
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t7e_flag_off_legacy_row_is_replaced_by_unavailable_exactly_as_at_the_parent(make_repo):
    row = Row("legacy summary", _legacy_meta(3))
    repo = make_repo(row, flag=False)
    incoming = _incoming("unavailable", text=MESSAGES["unavailable"])
    await repo.upsert(uuid4(), incoming)
    assert row.summary_text == MESSAGES["unavailable"]  # replaced, no notice
    expected_meta = {**_legacy_meta(3), **_incoming("unavailable")["summary_metadata"]}
    assert row.summary_metadata == expected_meta
    assert "last_refresh_outcome" not in row.summary_metadata
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["unavailable", "no_documents"])
async def test_t7e_flag_off_validated_clinical_row_still_gets_the_parent_preserve_with_notice(make_repo, outcome):
    row = Row("clinical", _clinical_meta())
    repo = make_repo(row, flag=False)
    await repo.upsert(uuid4(), _incoming(outcome))
    assert row.summary_text == NOTICE + "clinical"
    assert row.summary_metadata["last_refresh_outcome"]["processing_outcome"] == outcome
    assert row.summary_metadata["processing_outcome"] == "complete"


@pytest.mark.asyncio
async def test_t7e_flag_off_ordinary_merge_is_byte_identical_to_the_parent_formula(make_repo):
    previous = _clinical_meta(extra_key="keep-me", last_refresh_outcome={"x": 1})
    row = Row("old", copy.deepcopy(previous))
    repo = make_repo(row, flag=False)
    incoming = _incoming("complete")
    incoming["summary_metadata"].update(validation_status="passed", is_clinical_summary=True)
    expected = {**previous, **incoming["summary_metadata"]}
    expected.pop("last_refresh_outcome", None)
    await repo.upsert(uuid4(), incoming)
    assert row.summary_metadata == expected
