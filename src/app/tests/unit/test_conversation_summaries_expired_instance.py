"""FP4 regression: a repository method that rolls back and then returns an ORM row must return a
FULLY LOADED row, because callers immediately ``ConversationSummary.model_validate(row)`` it.

``session.rollback()`` expires every loaded instance (``expire_on_commit=False`` only affects
commit), so ``rollback(); return row`` hands back an empty-``__dict__`` row and pydantic raises
"Field required" for id/appointmentId/... -> the route answers HTTP 500. Mock-based tests cannot see
this, so these tests use a REAL SQLAlchemy session (see ``real_session_harness``).

Rollback-then-return paths covered (all in ``ConversationSummariesRepository``):
  A. ``upsert``  path (1)  -- ``no_visit_summary_documents`` must not overwrite a clinical row (FP4)
  B. ``upsert``  stale-attempt guard (a newer attempt already stored)
  C. ``upsert_many_for_source`` stale-attempt guard, non-empty ``rows``
  D. ``upsert_many_for_source`` stale-attempt guard, empty ``rows`` (``attempt_started_at`` kwarg)
Controls (never defective, kept as guards): the commit-based preserve branch and the create path.
The ``run_*`` scenarios are shared with the Postgres variant in ``pg_parity``.
"""

import copy
from unittest.mock import AsyncMock

import pytest

from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.tests.unit.real_session_harness import (
    PROCEDURE_SOURCE,
    SOURCE,
    USER,
    assert_fully_loaded_and_valid,
    make_row,
    seed,
    sqlite_engine,
    sqlite_session_factory,
    stored,
)
from uuid import uuid4

NEW = "no_visit_summary_documents"
CLINICAL = {
    "attempt_started_at": "2026-01-01T00:00:00+00:00",
    "processing_outcome": "complete",
    "validation_status": "passed",
    "is_clinical_summary": True,
    "successful_documents": 2,
}


def _payload(outcome, attempt, source=SOURCE, **meta):
    return {
        "summary_text": "placeholder",
        "user_id": USER,
        "created_by": USER,
        "updated_by": USER,
        "key_points": [],
        "medications": [],
        "diagnoses": [],
        "instructions": [],
        "recommendations": [],
        "data": {},
        "summary_metadata": {
            "source": source,
            "attempt_started_at": attempt,
            "processing_outcome": outcome,
            "validation_status": "not_applicable",
            "is_clinical_summary": False,
            **meta,
        },
    }


# ------------------------------------------------------------------ shared scenarios
async def run_path1_preserve(factory, make_repo, caplog=None):
    appt = uuid4()
    row = make_row(appt, metadata=CLINICAL)
    await seed(factory, row)
    before = await stored(factory, row.id)
    repo = make_repo(factory())
    returned = await repo.upsert(
        appt, _payload(NEW, "2026-02-01T00:00:00+00:00", regeneration_forced=False)
    )
    validated = assert_fully_loaded_and_valid(returned)
    assert validated.id == row.id and validated.summary_text == "real clinical summary"
    assert (
        await stored(factory, row.id) == before
    )  # byte-unchanged: nothing was written


async def run_stale_attempt_upsert(factory, make_repo):
    appt = uuid4()
    row = make_row(
        appt, metadata={**CLINICAL, "attempt_started_at": "2026-03-01T00:00:00+00:00"}
    )
    await seed(factory, row)
    before = await stored(factory, row.id)
    repo = make_repo(factory())
    returned = await repo.upsert(
        appt, _payload("complete", "2026-02-01T00:00:00+00:00")
    )
    validated = assert_fully_loaded_and_valid(returned)
    assert validated.id == row.id
    assert await stored(factory, row.id) == before


def _procedure_row(appt, attempt):
    return make_row(
        appt,
        source=PROCEDURE_SOURCE,
        text="procedure summary",
        metadata={
            "attempt_started_at": attempt,
            "source_document_ids": ["doc-1"],
            "validation_status": "passed",
        },
    )


async def run_stale_attempt_upsert_many(factory, make_repo, *, empty_rows):
    appt = uuid4()
    row = _procedure_row(appt, "2026-03-01T00:00:00+00:00")
    await seed(factory, row)
    before = await stored(factory, row.id)
    repo = make_repo(factory())
    if empty_rows:
        returned = await repo.upsert_many_for_source(
            appt,
            PROCEDURE_SOURCE,
            [],
            allow_prune=True,
            user_id=USER,
            attempt_started_at="2026-02-01T00:00:00+00:00",
        )
    else:
        incoming = _payload("complete", "2026-02-01T00:00:00+00:00", PROCEDURE_SOURCE)
        incoming["summary_metadata"]["source_document_ids"] = ["doc-1"]
        returned = await repo.upsert_many_for_source(appt, PROCEDURE_SOURCE, [incoming])
    assert len(returned) == 1
    validated = assert_fully_loaded_and_valid(returned[0])
    assert validated.id == row.id
    assert await stored(factory, row.id) == before


async def run_control_commit_preserve(factory, make_repo):
    """unavailable on a clinical row: committed (refreshed) path -- never defective."""
    appt = uuid4()
    row = make_row(appt, metadata=CLINICAL)
    await seed(factory, row)
    repo = make_repo(factory())
    returned = await repo.upsert(
        appt, _payload("unavailable", "2026-02-01T00:00:00+00:00")
    )
    validated = assert_fully_loaded_and_valid(returned)
    assert validated.id == row.id and validated.summary_text.endswith(
        "real clinical summary"
    )


async def run_control_create(factory, make_repo):
    appt = uuid4()
    repo = make_repo(factory())
    from src.app.db.objects.entities.conversation_summaries import (
        ConversationSummaries,
    )  # noqa: F401

    payload = _payload("complete", "2026-02-01T00:00:00+00:00")
    payload["id"] = uuid4()
    payload["summary_text"] = "fresh"
    returned = await repo.upsert(appt, payload)
    assert assert_fully_loaded_and_valid(returned).summary_text == "fresh"


# ------------------------------------------------------------------ sqlite (CI scope) tests
@pytest.fixture
def env(monkeypatch):
    engine = sqlite_engine()
    factory = sqlite_session_factory(engine)

    def make_repo(session):
        repo = ConversationSummariesRepository(session)
        # PostgreSQL advisory lock + SET LOCAL do not exist in SQLite; everything else is real.
        monkeypatch.setattr(repo, "_lock_scope", AsyncMock())
        return repo

    yield factory, make_repo
    engine.dispose()


async def test_a_path1_preserved_row_is_returned_fully_loaded(env):
    await run_path1_preserve(*env)


async def test_b_stale_attempt_upsert_returns_fully_loaded_row(env):
    await run_stale_attempt_upsert(*env)


async def test_c_stale_attempt_upsert_many_returns_fully_loaded_rows(env):
    await run_stale_attempt_upsert_many(*env, empty_rows=False)


async def test_d_stale_attempt_upsert_many_empty_rows_returns_fully_loaded_rows(env):
    await run_stale_attempt_upsert_many(*env, empty_rows=True)


async def test_control_commit_based_preserve_branch_is_valid(env):
    await run_control_commit_preserve(*env)


async def test_control_create_path_is_valid(env):
    await run_control_create(*env)


# ------------------------------------------------------------------ service level (real repo + real session)
async def test_service_returns_valid_summary_when_preserve_path_is_active(
    env, monkeypatch
):
    """FP4 end to end below the route: existing clinical row + all-non-allowlisted documents ->
    the service returns a valid ConversationSummary (the route therefore answers 200, not 500),
    the stored row is untouched, and no extraction / model work ran."""
    from src.app.tests.unit import (
        test_attachment_summarization_no_visit_summary_documents as t6,
    )

    factory, make_repo = env
    request = t6._request()
    row = make_row(
        request.appointment_id,
        metadata=CLINICAL,
        user_id=request.user_id,
        created_by=request.user_id,
        updated_by=request.user_id,
    )
    await seed(factory, row)
    before = await stored(factory, row.id)

    service = t6._service()  # candidates exist, allowlist rejected them all
    service.summaries_repo = make_repo(factory())
    t6._wire(monkeypatch, service, doc_references=[])

    result = await service.analyze_attachments(request)

    assert result.id == row.id and result.summary_text == "real clinical summary"
    assert result.metadata["processing_outcome"] == "complete"
    assert await stored(factory, row.id) == before
    assert service.llm_work == []
    assert any("No visit summary documents" in m for m in service.logs)
