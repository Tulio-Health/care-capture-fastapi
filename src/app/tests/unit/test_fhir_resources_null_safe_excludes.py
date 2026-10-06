"""Allowlist v2 prerequisite (b): the SELECTION query's NOT-exclude term must be NULL-safe.

`data->>'type'` is NULL for some documents, which makes every ILIKE/regex exclude clause NULL,
and `NOT (NULL)` is NULL, so such rows were silently dropped by the WHERE (the INVENTORY query
already coalesced). The fix wraps the OR in `coalesce(..., false)` for EVERY selection profile.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository

RULES = [
    {"action": "exclude", "matchStrategy": "ilike", "matchTarget": "type_text", "matchValue": "Education"},
    {"action": "exclude", "matchStrategy": "exact", "matchTarget": "type_text", "matchValue": "Billing"},
]
SNAPSHOT = (RULES, {"tier": "floor", "digest": "test"})


class _Inv:
    def all(self):
        return []


class _Sel:
    def scalars(self):
        return SimpleNamespace(all=lambda: [])


def _selection_sql(captured) -> str:
    return str(captured[1].compile(dialect=postgresql.dialect()))


async def _run(profile, rule_snapshot=SNAPSHOT):
    captured = []

    async def _execute(query, *a, **k):
        captured.append(query)
        return _Inv() if len(captured) == 1 else _Sel()

    repo = FhirResourcesRepository.__new__(FhirResourcesRepository)
    repo.session = SimpleNamespace(execute=AsyncMock(side_effect=_execute))
    await repo.get_document_references_with_attachments(
        user_id="u", encounter_id="e", selection_profile=profile, rule_snapshot=rule_snapshot
    )
    return captured


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["legacy", "visit_summary_preferred"])
async def test_selection_not_exclude_is_null_safe_for_every_profile(profile):
    sql = _selection_sql(await _run(profile))
    assert "NOT coalesce(" in sql
    # the OR of the exclude clauses sits INSIDE the coalesce, not outside it
    assert "NOT (" not in sql.replace("NOT coalesce(", "")


@pytest.mark.asyncio
async def test_no_exclude_rules_adds_no_not_term():
    sql = _selection_sql(await _run("legacy", ([], {"tier": "floor", "digest": "t"})))
    assert "NOT coalesce(" not in sql
