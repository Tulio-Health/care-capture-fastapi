"""Test helper: run FhirResourcesRepository.get_document_references_with_attachments against a
recording fake session and return the compiled SQL text + bound parameters of every statement.

Used by T1 (flag-off / other-profile SQL must equal the snapshot taken at the parent commit) and
by the allowlist selection tests.
"""

from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository

RULES = [
    {
        "action": "exclude",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "matchValue": "Education",
    },
    {
        "action": "exclude",
        "matchStrategy": "regex",
        "matchTarget": "type_text",
        "matchValue": "^Edu",
    },
    {
        "action": "exclude",
        "matchStrategy": "exact",
        "matchTarget": "type_text",
        "matchValue": "Billing",
        "sourceEmr": "cerner",
    },
    {
        "action": "exclude",
        "matchStrategy": "exact",
        "matchTarget": "loinc_code",
        "matchValue": "12345-6",
    },
    {
        "action": "include",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "matchValue": "Note",
    },
    {
        "action": "prefer",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "matchValue": "Depart Summary",
    },
    {
        "action": "resolve",
        "documentClass": "visit_summary",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "matchValue": "AVS",
    },
]
PROVENANCE = {"tier": "live", "digest": "snapshot-test"}

SCENARIOS = {
    "legacy_with_rules": ("legacy", RULES),
    "legacy_no_rules": ("legacy", []),
    "visit_summary_preferred_with_rules": ("visit_summary_preferred", RULES),
    "visit_summary_preferred_no_rules": ("visit_summary_preferred", []),
    "comprehensive_profile_name_with_rules": ("comprehensive", RULES),
}


class FakeInventoryResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows


class FakeSelectionResult:
    def __init__(self, resources=()):
        self._resources = list(resources)

    def scalars(self):
        return SimpleNamespace(all=lambda: self._resources)


class FakeExistsResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def first(self):
        return (1,) if self._value else None


def compile_statement(statement):
    compiled = statement.compile(dialect=postgresql.dialect())
    params = {
        k: (v if isinstance(v, (str, int, float, bool, type(None))) else repr(v))
        for k, v in compiled.params.items()
    }
    return {"sql": str(compiled), "params": dict(sorted(params.items()))}


async def run_repo(
    profile,
    rules,
    *,
    inventory=(),
    selection=(),
    exists=None,
    repo=None,
    rule_snapshot=True,
):
    """Execute one repo call; returns (repo, [compiled statements]). `exists` is the value the
    discriminator EXISTS query returns when it is issued (third statement)."""
    statements = []

    async def _execute(statement, *args, **kwargs):
        statements.append(statement)
        position = len(statements)
        if position == 1:
            return FakeInventoryResult(inventory)
        if position == 2:
            return FakeSelectionResult(selection)
        return FakeExistsResult(bool(exists))

    from unittest.mock import AsyncMock

    repo = repo or FhirResourcesRepository.__new__(FhirResourcesRepository)
    repo.session = SimpleNamespace(execute=AsyncMock(side_effect=_execute))
    await repo.get_document_references_with_attachments(
        user_id="user-1",
        encounter_id="enc-1",
        selection_profile=profile,
        rule_snapshot=(rules, PROVENANCE) if rule_snapshot else None,
    )
    return repo, [compile_statement(s) for s in statements]
