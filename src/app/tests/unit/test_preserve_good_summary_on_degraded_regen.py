"""Safety net: a failed/degraded regeneration never degrades an existing good attachment-summary row
(PRESERVE_GOOD_SUMMARY_ON_DEGRADED_REGEN), and the attempt is reported via `attempt_outcome` /
the async signal `outcome`."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.app.db.objects.repositories import conversation_summaries as cs_mod
from src.app.db.objects.repositories.conversation_summaries import (
    PRESERVED_EXISTING,
    ConversationSummariesRepository,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.services import async_dispatch

USER = uuid4()
NOTICE = "We couldn’t update this summary"


class Row:
    def __init__(self, text, meta):
        self.id = uuid4()
        self.user_id = USER
        self.summary_text = text
        self.summary_metadata = meta
        self.key_points = ["kp"]
        self.medications = [{"name": "m"}]
        self.diagnoses = ["d"]
        self.instructions = []
        self.recommendations = []
        self.data = {}
        self.updated_by = USER


def _snap(row):
    return copy.deepcopy({k: v for k, v in vars(row).items() if k != "attempt_outcome"})


def _stored(outcome="complete", errors=0):
    return {"source": "attachment_summary", "attempt_started_at": "2026-01-01T00:00:00+00:00",
            "processing_outcome": outcome, "validation_status": "passed", "processing_error_count": errors}


LEGACY = {"source": "attachment_summary", "successful_documents": 2, "analysis_version": "2.1"}


def _incoming(outcome, errors=0):
    return {
        "summary_text": "new text", "user_id": USER, "created_by": USER, "updated_by": USER,
        "key_points": ["new"], "medications": [], "diagnoses": [], "instructions": [],
        "recommendations": [], "data": {},
        "summary_metadata": {
            "source": "attachment_summary", "attempt_started_at": "2026-02-01T00:00:00+00:00",
            "processing_outcome": outcome, "processing_error_count": errors,
            "validation_status": "passed" if outcome in {"complete", "partial"} else "not_applicable",
        },
    }


@pytest.fixture
def make_repo(monkeypatch):
    def _make(row, *, preserve=True):
        monkeypatch.setattr(cs_mod, "get_settings", lambda: SimpleNamespace(
            VISIT_SUMMARY_ALLOWLIST_ENABLED=False, PRESERVE_GOOD_SUMMARY_ON_DEGRADED_REGEN=preserve))
        session = MagicMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        repo = ConversationSummariesRepository(session)
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_by_appointment_id_and_source", AsyncMock(return_value=row))
        monkeypatch.setattr(repo, "_commit_validated", AsyncMock())
        return repo
    return _make


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["unavailable", "no_documents", "partial"])
async def test_degraded_over_legacy_keeps_row_byte_identical(make_repo, outcome, caplog):
    row = Row("legacy summary text", dict(LEGACY))
    before = _snap(row)
    repo = make_repo(row)
    with caplog.at_level("WARNING"):
        result = await repo.upsert(uuid4(), _incoming(outcome, errors=2))
    assert result is row and _snap(row) == before
    assert NOTICE not in row.summary_text
    assert "last_refresh_outcome" not in row.summary_metadata
    assert row.attempt_outcome == PRESERVED_EXISTING
    repo._commit_validated.assert_not_awaited()
    assert "preserved_existing_summary_on_degraded_regen" in caplog.text


@pytest.mark.asyncio
async def test_partial_with_failed_chunks_over_complete_keeps_old(make_repo):
    row = Row("complete text", _stored("complete"))
    before = _snap(row)
    result = await make_repo(row).upsert(uuid4(), _incoming("partial", errors=3))
    assert _snap(row) == before and result.attempt_outcome == PRESERVED_EXISTING


@pytest.mark.asyncio
async def test_partial_with_more_errors_than_stored_partial_keeps_old(make_repo):
    row = Row("partial text", _stored("partial", errors=1))
    before = _snap(row)
    await make_repo(row).upsert(uuid4(), _incoming("partial", errors=4))
    assert _snap(row) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [dict(LEGACY), _stored("complete"), _stored("partial", 2)])
async def test_new_complete_replaces_old_row(make_repo, stored):
    row = Row("old text", stored)
    repo = make_repo(row)
    result = await repo.upsert(uuid4(), _incoming("complete"))
    assert result.summary_text == "new text"
    assert getattr(result, "attempt_outcome", None) is None
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_with_fewer_errors_replaces_stored_partial(make_repo):
    row = Row("old", _stored("partial", errors=3))
    repo = make_repo(row)
    result = await repo.upsert(uuid4(), _incoming("partial", errors=1))
    assert result.summary_text == "new text"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "partial", "unavailable"])
async def test_first_ever_summary_is_written_normally(make_repo, outcome):
    repo = make_repo(None)
    result = await repo.upsert(uuid4(), _incoming(outcome))
    repo.session.add.assert_called_once()
    repo._commit_validated.assert_awaited_once()
    assert getattr(result, "attempt_outcome", None) is None


@pytest.mark.asyncio
async def test_unavailable_over_unavailable_row_is_not_protected(make_repo):
    row = Row("We couldn’t create a summary", _stored("unavailable"))
    repo = make_repo(row)
    await repo.upsert(uuid4(), _incoming("unavailable"))
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_legacy_row_is_not_good(make_repo):
    row = Row("   ", dict(LEGACY))
    repo = make_repo(row)
    await repo.upsert(uuid4(), _incoming("unavailable"))
    repo._commit_validated.assert_awaited_once()


@pytest.mark.asyncio
async def test_flag_off_restores_notice_behaviour(make_repo):
    row = Row("legacy summary text", dict(LEGACY))
    repo = make_repo(row, preserve=False)
    # legacy row is only "clinical" under the allowlist flag; use a validated complete row
    row2 = Row("complete text", _stored("complete"))
    repo = make_repo(row2, preserve=False)
    result = await repo.upsert(uuid4(), _incoming("unavailable"))
    assert result.summary_text.startswith(NOTICE)
    assert "last_refresh_outcome" in result.summary_metadata
    assert getattr(result, "attempt_outcome", None) is None


def test_response_model_carries_attempt_outcome():
    from datetime import datetime, timezone
    row = Row("t", {"source": "attachment_summary"})
    row.appointment_id = uuid4()
    row.created_at = row.updated_at = datetime.now(timezone.utc)
    row.created_by = USER
    row.attempt_outcome = PRESERVED_EXISTING
    assert ConversationSummary.model_validate(row).attempt_outcome == PRESERVED_EXISTING
    del row.attempt_outcome
    assert ConversationSummary.model_validate(row).attempt_outcome is None


class _FakeRedis:
    def __init__(self):
        self.calls = []

    def set(self, key, value, ex=None):
        self.calls.append((key, json.loads(value)))


@pytest.mark.asyncio
async def test_async_signal_carries_outcome_and_stays_backward_compatible(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(async_dispatch, "_get_signal_redis", lambda: fake)
    monkeypatch.setattr(async_dispatch, "_bg_slots", asyncio.Semaphore(2))

    async def preserved():
        return PRESERVED_EXISTING

    async def plain():
        return None

    await async_dispatch._run(preserved, "a1", "attachment_summary", "tok")
    key, body = fake.calls[-1]
    assert key.endswith(":summary:async:done:a1:attachment_summary:tok")
    assert body == {"status": "succeeded", "reason_code": None, "token": "tok", "outcome": PRESERVED_EXISTING}
    await async_dispatch._run(plain, "a1", "attachment_summary", "tok2")
    assert fake.calls[-1][1] == {"status": "succeeded", "reason_code": None, "token": "tok2"}
