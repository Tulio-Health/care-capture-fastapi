"""
PR-3: persistence-layer corrective fixes for `ConversationSummariesRepository`.

Pure-mock safety-guard tests for the hardening hunks applied on top of the PR-2
upsert-then-prune rewrite:
  1. Keyless rows are retained (never silently pruned).
  2. Heterogeneous owner in an incoming `rows` batch is rejected.
  3. `55P03` (lock_timeout) is retried exactly once via `_retry_transaction`.
  4. A staleness early-return rolls back the transaction (releases the advisory lock).
  5. `_attempt_at` normalizes 'Z' vs '+00:00' timestamps for the same instant.
  6. `appointment_belongs_to` (PR-1's shared predicate) is True only for the real owner.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
    _attempt_at,
    appointment_belongs_to,
)


def _make_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _existing_row(user_id, document_ids=None, attempt_started_at="", validation_status="passed"):
    row = MagicMock()
    row.user_id = user_id
    row.summary_metadata = {
        "attempt_started_at": attempt_started_at,
        "validation_status": validation_status,
        **({"source_document_ids": document_ids} if document_ids is not None else {}),
    }
    row.summary_text = "existing text"
    return row


class TestKeylessRowRetention:
    @pytest.mark.asyncio
    async def test_keyless_row_survives_prune_pass(self, monkeypatch):
        """A row with no source_document_ids must never land in stale_rows / get deleted,
        even when allow_prune=True and the incoming batch matches nothing else."""
        user_id = uuid4()
        appointment_id = uuid4()
        keyless = _existing_row(user_id, document_ids=None)

        repo = ConversationSummariesRepository(_make_session())
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_all_by_appointment_id_and_source", AsyncMock(return_value=[keyless]))
        monkeypatch.setattr(repo, "_commit_validated", AsyncMock())

        incoming_row = {
            "user_id": user_id,
            "summary_metadata": {"source": "procedure_summary", "source_document_ids": ["doc-1"]},
        }
        await repo.upsert_many_for_source(appointment_id, "procedure_summary", [incoming_row], allow_prune=True)

        repo.session.delete.assert_not_called()
        commit_call = repo._commit_validated.call_args
        assert keyless not in commit_call.kwargs.get("deleted_ids", commit_call.args[1] if len(commit_call.args) > 1 else ())


class TestHeterogeneousOwnerRejection:
    @pytest.mark.asyncio
    async def test_mixed_user_id_rows_raise_scope_mismatch(self, monkeypatch):
        repo = ConversationSummariesRepository(_make_session())
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_all_by_appointment_id_and_source", AsyncMock(return_value=[]))

        owner = uuid4()
        stranger = uuid4()
        rows = [
            {"user_id": owner, "summary_metadata": {"source_document_ids": ["doc-1"]}},
            {"user_id": stranger, "summary_metadata": {"source_document_ids": ["doc-2"]}},
        ]

        with pytest.raises(ValueError, match="SUMMARY_SCOPE_MISMATCH"):
            await repo.upsert_many_for_source(uuid4(), "procedure_summary", rows, allow_prune=True)

        repo.session.rollback.assert_awaited()


class TestRetrySqlstate:
    @pytest.mark.asyncio
    async def test_55p03_is_retried_once_then_succeeds(self):
        from src.app.db.objects.repositories.conversation_summaries import _retry_transaction

        class FakeDbError(Exception):
            orig = type("orig", (), {"sqlstate": "55P03"})()

        calls = {"n": 0}

        class Dummy:
            def __init__(self):
                self.session = MagicMock()
                self.session.rollback = AsyncMock()

            @_retry_transaction
            async def op(self):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise FakeDbError("lock_timeout")
                return "ok"

        dummy = Dummy()
        result = await dummy.op()

        assert result == "ok"
        assert calls["n"] == 2
        dummy.session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_55p03_fails_after_single_retry(self):
        from src.app.db.objects.repositories.conversation_summaries import _retry_transaction

        class FakeDbError(Exception):
            orig = type("orig", (), {"sqlstate": "55P03"})()

        calls = {"n": 0}

        class Dummy:
            def __init__(self):
                self.session = MagicMock()
                self.session.rollback = AsyncMock()

            @_retry_transaction
            async def op(self):
                calls["n"] += 1
                raise FakeDbError("lock_timeout")

        dummy = Dummy()
        with pytest.raises(FakeDbError):
            await dummy.op()

        assert calls["n"] == 2  # exactly one retry, then re-raise
        dummy.session.rollback.assert_awaited_once()


class TestStaleAttemptRollback:
    @pytest.mark.asyncio
    async def test_upsert_many_for_source_rolls_back_on_staleness_early_return(self, monkeypatch):
        user_id = uuid4()
        appointment_id = uuid4()
        newer_existing = _existing_row(user_id, document_ids=["doc-1"], attempt_started_at="2025-01-02T00:00:00+00:00")

        repo = ConversationSummariesRepository(_make_session())
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_all_by_appointment_id_and_source", AsyncMock(return_value=[newer_existing]))

        stale_incoming = [{
            "user_id": user_id,
            "summary_metadata": {"source_document_ids": ["doc-1"], "attempt_started_at": "2025-01-01T00:00:00+00:00"},
        }]

        result = await repo.upsert_many_for_source(appointment_id, "procedure_summary", stale_incoming, allow_prune=True)

        assert result == [newer_existing]
        repo.session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_upsert_rolls_back_on_staleness_early_return(self, monkeypatch):
        user_id = uuid4()
        appointment_id = uuid4()
        existing = MagicMock()
        existing.user_id = user_id
        existing.summary_metadata = {"attempt_started_at": "2025-01-02T00:00:00+00:00"}

        repo = ConversationSummariesRepository(_make_session())
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        monkeypatch.setattr(repo, "_validate_payload", MagicMock())
        monkeypatch.setattr(repo, "get_by_appointment_id_and_source", AsyncMock(return_value=existing))

        summary_data = {
            "user_id": user_id,
            "summary_metadata": {"source": "transcript", "attempt_started_at": "2025-01-01T00:00:00+00:00"},
        }

        result = await repo.upsert(appointment_id, summary_data)

        assert result is existing
        repo.session.rollback.assert_awaited()


class TestAttemptAtNormalization:
    def test_z_and_offset_suffix_compare_equal_for_same_instant(self):
        z_form = _attempt_at("2025-01-01T12:00:00Z")
        offset_form = _attempt_at("2025-01-01T12:00:00+00:00")

        assert z_form == offset_form
        assert not (z_form > offset_form)

        # Prove this is the exact bug the raw-string comparison had: as plain strings,
        # 'Z' (ord 90) sorts AFTER '+00:00' (ord 43 for '+') even though the instants are
        # equal - a naive `>` comparison would have wrongly called the Z-suffixed row newer.
        assert "2025-01-01T12:00:00Z" > "2025-01-01T12:00:00+00:00"
        assert "2025-01-01T12:00:00Z" != "2025-01-01T12:00:00+00:00"  # never equal as raw strings

    def test_missing_value_sorts_older_than_any_real_timestamp(self):
        assert _attempt_at("") < _attempt_at("2025-01-01T00:00:00Z")

    def test_naive_timestamp_treated_as_utc(self):
        naive = _attempt_at("2025-01-01T12:00:00")
        aware = _attempt_at("2025-01-01T12:00:00+00:00")
        assert naive == aware


class TestAppointmentBelongsTo:
    @pytest.mark.asyncio
    async def test_returns_true_for_owned_appointment(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = uuid4()
        session.execute.return_value = result_mock

        assert await appointment_belongs_to(session, uuid4(), uuid4()) is True

    @pytest.mark.asyncio
    async def test_returns_false_for_foreign_appointment(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        assert await appointment_belongs_to(session, uuid4(), uuid4()) is False
