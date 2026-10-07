"""FP4 regression in a REAL PostgreSQL through the application's runtime driver (asyncpg) and a real
``AsyncSession``: rollback-then-return paths must hand back fully loaded rows.

Same scenarios as ``unit/test_conversation_summaries_expired_instance.py`` (which runs them on SQLite in
the CI unit scope); here the real ``_lock_scope`` (advisory lock + ``SET LOCAL``) also runs.

Marker ``pg_parity``; needs ``PARITY_PG_DSN`` AND ``PARITY_PG_ALLOW_WRITES=1`` because it creates and
drops its own table in a THROWAWAY database (never point it at a shared one).
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.tests.unit import test_conversation_summaries_expired_instance as scenarios
from src.app.tests.unit.real_session_harness import USER

pytestmark = pytest.mark.pg_parity

DSN = os.environ.get("PARITY_PG_DSN")
if not DSN or os.environ.get("PARITY_PG_ALLOW_WRITES") != "1":
    pytest.skip(
        "PARITY_PG_DSN / PARITY_PG_ALLOW_WRITES=1 not set", allow_module_level=True
    )

DDL = """
CREATE TABLE conversation_summaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id uuid NOT NULL,
    user_id uuid NOT NULL,
    summary_text text NOT NULL,
    key_points json, medications json, diagnoses json, instructions json, recommendations json,
    metadata json, data json,
    created_at timestamptz DEFAULT timezone('utc', now()),
    updated_at timestamptz DEFAULT timezone('utc', now()),
    created_by uuid NOT NULL,
    updated_by uuid NOT NULL
);
CREATE TABLE appointments (id uuid PRIMARY KEY, user_id varchar);
"""


@pytest.fixture
async def env():
    url = DSN.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(
            text("DROP TABLE IF EXISTS conversation_summaries, appointments")
        )
        for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
            await conn.execute(text(stmt))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class Factory:
        """Seeds the appointments table so the real ownership check in `_lock_scope` passes."""

        opened = []

        def __call__(self):
            session = maker()
            self.opened.append(session)
            return session

    async def _own(appointment_id):
        async with maker() as s:
            await s.execute(
                text(
                    "INSERT INTO appointments (id, user_id) VALUES (:i, :u) ON CONFLICT DO NOTHING"
                ),
                {"i": appointment_id, "u": str(USER)},
            )
            await s.commit()

    factory = Factory()
    original_seed = scenarios.seed

    async def seed_and_own(f, *rows):
        for row in rows:
            await _own(row.appointment_id)
        await original_seed(f, *rows)

    scenarios.seed = seed_and_own
    yield factory, ConversationSummariesRepository
    scenarios.seed = original_seed
    for (
        session
    ) in factory.opened:  # request-scoped sessions are closed by `get_db`; an open
        await session.close()  # post-refresh transaction would block the DROP TABLE below
    async with engine.begin() as conn:
        await conn.execute(
            text("DROP TABLE IF EXISTS conversation_summaries, appointments")
        )
    await engine.dispose()


async def test_pg_a_path1_preserved_row_is_fully_loaded(env):
    await scenarios.run_path1_preserve(*env)


async def test_pg_b_stale_attempt_upsert_is_fully_loaded(env):
    await scenarios.run_stale_attempt_upsert(*env)


async def test_pg_c_stale_attempt_upsert_many_is_fully_loaded(env):
    await scenarios.run_stale_attempt_upsert_many(*env, empty_rows=False)


async def test_pg_d_stale_attempt_upsert_many_empty_rows_is_fully_loaded(env):
    await scenarios.run_stale_attempt_upsert_many(*env, empty_rows=True)
