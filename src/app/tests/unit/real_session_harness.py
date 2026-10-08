"""Real-ORM-session harness for the "returned ORM instance was expired by a rollback" regression.

Why this exists: unit tests that mock the session never expire instances, so they cannot see that
``session.rollback()`` EXPIRES every loaded instance (``expire_on_commit=False`` only covers commit).
A repository method that does ``rollback(); return row`` hands its caller an expired row, and the
service's ``ConversationSummary.model_validate(row)`` then reads an empty ``__dict__`` and raises
(FP4 on dev: HTTP 500 "The summary could not be validated safely").

Two interchangeable session sources, same scenarios:

* ``sqlite_session_factory`` -- in-memory SQLite through a REAL sync ``sqlalchemy.orm.Session`` wrapped
  by a thin awaitable adapter (``aiosqlite`` is not a project dependency, and adding one would change
  the lockfile). Expiry/refresh/identity-map semantics are SQLAlchemy's own, so the defect reproduces
  exactly. Needs no external service -> runs in the CI unit scope. The PostgreSQL-only advisory lock
  (``_lock_scope``) is stubbed by the caller; everything else in the repository runs for real.
* the ``pg_parity`` variant (``src/app/tests/pg_parity/test_expired_instance_pg.py``) drives the same
  scenarios through a real asyncpg ``AsyncSession`` against a throwaway PostgreSQL.
"""

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app.db.objects.entities.conversation_summaries import ConversationSummaries
from src.app.models.conversation_summaries import ConversationSummary

USER = uuid4()
SOURCE = "attachment_summary"
PROCEDURE_SOURCE = "procedure_summary"


class SyncBackedAsyncSession:
    """Awaitable facade over a real sync ``Session`` (only what the repository uses)."""

    def __init__(self, session: Session):
        self._s = session

    async def execute(self, *a, **k):
        return self._s.execute(*a, **k)

    async def flush(self):
        self._s.flush()

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def refresh(self, obj):
        self._s.refresh(obj)

    async def delete(self, obj):
        self._s.delete(obj)

    def add(self, obj):
        self._s.add(obj)

    async def close(self):
        self._s.close()


def sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fns(dbapi_conn, _):  # the entity's server defaults/onupdate use PG functions
        dbapi_conn.create_function(
            "NOW", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        )
        dbapi_conn.create_function("TIMEZONE", 2, lambda _tz, ts: ts)

    ConversationSummaries.__table__.create(engine)
    return engine


def sqlite_session_factory(engine):
    return lambda: SyncBackedAsyncSession(Session(engine, expire_on_commit=False))


def make_row(
    appointment_id, *, metadata, source=SOURCE, text="real clinical summary", **extra
):
    now = datetime.now(timezone.utc)
    values = dict(
        id=uuid4(),
        appointment_id=appointment_id,
        user_id=USER,
        created_by=USER,
        updated_by=USER,
        summary_text=text,
        key_points=["kp"],
        medications=[{"name": "m"}],
        diagnoses=["d"],
        instructions=["i"],
        recommendations=[{"r": 1}],
        data={"procedures_mentioned": ["p"]},
        summary_metadata={"source": source, **metadata},
        created_at=now,
        updated_at=now,
    )
    values.update(extra)
    return ConversationSummaries(**values)


async def seed(session_factory, *rows):
    """Persist rows in their OWN session, like an earlier request did."""
    session = session_factory()
    for row in rows:
        session.add(row)
    await session.commit()
    await session.close()


def assert_fully_loaded_and_valid(returned):
    """Do exactly what the service does with the repository result, then check every field."""
    validated = ConversationSummary.model_validate(returned)
    assert validated.id and validated.appointment_id and validated.user_id
    assert validated.summary_text
    assert validated.created_at and validated.updated_at and validated.created_by
    assert validated.metadata and validated.metadata.get("source")
    return validated


async def stored(session_factory, row_id):
    """Fresh read of the committed row as a plain dict (proves nothing was written)."""
    session = session_factory()
    from sqlalchemy import select

    row = (
        await session.execute(
            select(ConversationSummaries).where(ConversationSummaries.id == row_id)
        )
    ).scalar_one()
    snapshot = {
        c.key: getattr(row, c.key)
        for c in ConversationSummaries.__mapper__.column_attrs
    }
    await session.close()
    return snapshot
