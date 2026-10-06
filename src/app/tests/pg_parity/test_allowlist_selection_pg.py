"""End-to-end SELECTION semantics of the allowlist in a real PostgreSQL (CI throwaway / local).

Creates the ``fhir_resources`` table in a scratch schema, inserts one encounter's DocumentReferences
and runs the REAL ``FhirResourcesRepository.get_document_references_with_attachments`` through
asyncpg. Needs write access, so it additionally requires ``PARITY_PG_ALLOW_WRITES=1`` and is
skipped otherwise (never run it against a shared database).
"""
import os
import re
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.db.models.fhir_resources import FhirResource
from src.app.db.objects.repositories import fhir_resources as repo_mod
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository

pytestmark = pytest.mark.pg_parity

DSN = os.environ.get("PARITY_PG_DSN")
if not DSN or os.environ.get("PARITY_PG_ALLOW_WRITES") != "1":
    pytest.skip("PARITY_PG_DSN and PARITY_PG_ALLOW_WRITES=1 are required", allow_module_level=True)

SCHEMA = "allowlist_selection_parity"
USER, ENC = "user_1", "enc_1"
LOINC = "http://loinc.org"
RULES = [
    {"action": "exclude", "matchStrategy": "ilike", "matchTarget": "type_text", "matchValue": "Billing"},
    {"action": "prefer", "matchStrategy": "ilike", "matchTarget": "type_text", "matchValue": "Depart Summary"},
]
SNAPSHOT = (RULES, {"tier": "live", "digest": "pg"})


def _docs():
    def d(rid, label, date, **extra):
        data = {"encounterReference": f"Encounter/{ENC}", "date": date, "attachments": [{"url": "s3://b/k"}], **extra}
        if label is not None:
            data["type"] = label
        return rid, data

    return [
        d("progress", "Progress Note", "2026-01-05"),
        d("depart", "Depart Summary", "2026-01-04"),
        d("imaging", "Diagnostic Imaging Study", "2026-01-03"),
        d("instructions", "Patient Instructions", "2026-01-02"),
        d("billing", "Billing Statement", "2026-01-01"),  # DB-excluded
        d("null_plain", None, "2026-01-06"),  # NULL type, no LOINC -> not allowlisted, but NOT dropped by excludes
        d("null_loinc", None, "2026-01-07", typeCode="11506-3", typeSystem=LOINC),  # LOINC-only -> allowlisted
        d("epic_oid", None, "2026-01-08", typeCode="11506-3", typeSystem="urn:oid:1.2.840.114350.1.13.0.1.7.2.688879"),
        d("nursing", "ED Note Nursing", "2026-01-09"),  # include AND deny -> denied
        d("no_attach", "Progress Note", "2026-01-10", attachments=[]),
    ]


@pytest.fixture
async def session_factory():
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+asyncpg://", DSN)
    url = re.sub(r"([?&])sslmode=[^&]*&?", r"\1", url).rstrip("?&")
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": SCHEMA}})
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await conn.run_sync(lambda c: FhirResource.__table__.create(c))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for rid, data in _docs():
            session.add(
                FhirResource(
                    user_id=USER, resource_type="DocumentReference", ehr_resource_id=rid, ehr_connection_id=uuid.uuid4(),
                    data=data, ehr_provider="CERNER", ehr_provider_id=uuid.uuid4(),
                )
            )
        await session.commit()
    yield factory
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    await engine.dispose()


def _flag(monkeypatch, value):
    from types import SimpleNamespace

    monkeypatch.setattr(repo_mod, "get_settings", lambda: SimpleNamespace(VISIT_SUMMARY_ALLOWLIST_ENABLED=value))


async def _fetch(factory, profile):
    async with factory() as session:
        repo = FhirResourcesRepository(session)
        rows = await repo.get_document_references_with_attachments(
            user_id=USER, encounter_id=ENC, selection_profile=profile, rule_snapshot=SNAPSHOT
        )
        return repo, [r.ehr_resource_id for r in rows]


@pytest.mark.asyncio
async def test_flag_off_visit_summary_keeps_everything_not_db_excluded_incl_null_type(session_factory, monkeypatch):
    _flag(monkeypatch, False)
    repo, ids = await _fetch(session_factory, "visit_summary_preferred")
    assert set(ids) == {"progress", "depart", "imaging", "instructions", "null_plain", "null_loinc", "epic_oid", "nursing"}
    assert ids[0] == "depart"  # prefer rule still ranks first
    assert repo.visit_summary_selection is None


@pytest.mark.asyncio
async def test_flag_on_visit_summary_selects_only_allowlisted(session_factory, monkeypatch):
    _flag(monkeypatch, True)
    repo, ids = await _fetch(session_factory, "visit_summary_preferred")
    assert set(ids) == {"progress", "depart", "null_loinc"}
    assert ids[0] == "depart"
    assert repo.non_allowlisted_candidates_exist is False
    tele = repo.visit_summary_selection
    assert tele["not_allowlisted_documents"] == 5  # imaging, instructions, null_plain, epic_oid, nursing
    assert tele["not_allowlisted_types"] == {
        "(null)": 2, "diagnostic imaging study": 1, "ed note nursing": 1, "patient instructions": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["legacy", "comprehensive"])
async def test_flag_on_other_profiles_are_unfiltered(session_factory, monkeypatch, profile):
    _flag(monkeypatch, True)
    _repo, ids = await _fetch(session_factory, profile)
    assert set(ids) == {"progress", "depart", "imaging", "instructions", "null_plain", "null_loinc", "epic_oid", "nursing"}


@pytest.mark.asyncio
async def test_empty_selection_discriminator_against_real_rows(session_factory, monkeypatch):
    _flag(monkeypatch, True)
    async with session_factory() as session:
        await session.execute(text(
            "DELETE FROM fhir_resources WHERE ehr_resource_id IN ('progress','depart','null_loinc')"
        ))
        await session.commit()
    repo, ids = await _fetch(session_factory, "visit_summary_preferred")
    assert ids == [] and repo.non_allowlisted_candidates_exist is True
    async with session_factory() as session:
        await session.execute(text("DELETE FROM fhir_resources"))
        await session.commit()
    repo, ids = await _fetch(session_factory, "visit_summary_preferred")
    assert ids == [] and repo.non_allowlisted_candidates_exist is False
