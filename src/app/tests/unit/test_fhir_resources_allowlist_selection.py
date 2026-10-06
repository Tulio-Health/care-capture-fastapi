"""T1-T5 / T2b -- visit-summary allowlist v2 in the repository SELECTION query.

* T1  flag off (any profile) and flag on for every OTHER profile: compiled SQL + params of both
      statements are IDENTICAL to the snapshot taken at the parent commit.
* T2  flag on + visit_summary_preferred: the allow term is a WHERE term (before LIMIT cap+1), the
      INVENTORY statement is unchanged, ORDER BY unchanged, patterns are bind params.
* T2b reset-per-call + discriminator + LOINC-only docs.
* T3/T4 procedure / comprehensive profile isolation (regression for BLOCKER r2-f-01).
* T5  empty-selection discriminator semantics and telemetry caps.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.db.objects.repositories import fhir_resources as repo_mod
from src.app.services import visit_summary_allowlist as al
from src.app.tests.unit.fhir_selection_capture import RULES, SCENARIOS, run_repo

SNAPSHOT = json.loads(
    (
        Path(__file__).parent / "snapshots" / "fhir_resources_selection_sql.json"
    ).read_text()
)


@pytest.fixture
def flag(monkeypatch):
    def _set(value: bool):
        monkeypatch.setattr(
            repo_mod,
            "get_settings",
            lambda: SimpleNamespace(VISIT_SUMMARY_ALLOWLIST_ENABLED=value),
        )

    _set(False)
    return _set


def _doc(rid, label, *, code=None, system=None, attachments=True, date="2026-01-01"):
    data = {
        "type": label,
        "date": date,
        "attachments": [{"url": "s3://x"}] if attachments else [],
    }
    if code is not None:
        data["typeCode"] = code
    if system is not None:
        data["typeSystem"] = system
    return SimpleNamespace(
        ehr_resource_id=rid, data=data, updated_at="2026-01-01T00:00:00Z"
    )


# ---------------------------------------------------------------------------------------------
# T1: flag off == parent commit, for every scenario
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_t1_flag_off_sql_and_params_equal_parent_snapshot(flag, name):
    flag(False)
    profile, rules = SCENARIOS[name]
    repo, stmts = await run_repo(profile, rules)
    assert stmts == SNAPSHOT[name]
    assert (
        repo.visit_summary_selection is None
        and repo.non_allowlisted_candidates_exist is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [n for n, (p, _r) in sorted(SCENARIOS.items()) if p != "visit_summary_preferred"],
)
async def test_t1_flag_on_other_profiles_equal_parent_snapshot(flag, name):
    flag(True)
    profile, rules = SCENARIOS[name]
    repo, stmts = await run_repo(profile, rules, exists=True)
    assert (
        stmts == SNAPSHOT[name]
    )  # no allow term, and NO third (discriminator) statement
    assert (
        repo.visit_summary_selection is None
        and repo.non_allowlisted_candidates_exist is False
    )


# ---------------------------------------------------------------------------------------------
# T2: flag on + visit_summary_preferred
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["visit_summary_preferred_with_rules", "visit_summary_preferred_no_rules"]
)
async def test_t2_allow_term_is_a_where_term_before_the_limit(flag, name):
    flag(True)
    profile, rules = SCENARIOS[name]
    _repo, stmts = await run_repo(
        profile, rules, selection=[_doc("a", "Progress Note")]
    )
    assert len(stmts) == 2  # non-empty selection: no discriminator query
    inventory, selection = stmts
    # INVENTORY query is UNCHANGED (hard requirement: manifest equality downstream)
    assert inventory == SNAPSHOT[name][0]
    parent_sel = SNAPSHOT[name][1]
    sel_sql = selection["sql"]
    where, _, tail = sel_sql.partition("ORDER BY")
    assert "regexp_replace" in where and " ~ " in where
    assert where.count("coalesce(") > parent_sel["sql"].partition("ORDER BY")[0].count(
        "coalesce("
    )
    # ORDER BY ... LIMIT segment is unchanged. Bind-parameter NUMBERING shifts when WHERE terms are
    # added, so compare with the numbering normalized; the parent's parameter VALUES must all
    # still be present (checked below).
    norm = lambda text: re.sub(r"%\((\w+?)(_\d+)?\)s", r"%(\1)s", text)  # noqa: E731
    assert norm("ORDER BY" + tail) == norm(
        "ORDER BY" + parent_sel["sql"].partition("ORDER BY")[2]
    )
    # the two alternations, the LOINC OID and the whitespace class travel as bind params
    values = [v for v in selection["params"].values()]
    assert al.include_regex() in values and al.deny_regex() in values
    assert al.LOINC_OID in values and al.WS_CLASS_SQL in values
    assert (
        repr(list(al.LOINC_ALLOW_CODES)) in values
    )  # expanding IN (...) parameter (repr'd by the capture helper)
    assert any(
        v == 51 for v in selection["params"].values()
    )  # LIMIT DOCUMENT_SELECTION_CAP + 1
    # every parent parameter VALUE is still bound (multiset containment)
    from collections import Counter

    new_counts = Counter(repr(v) for v in selection["params"].values())
    for value, count in Counter(repr(v) for v in parent_sel["params"].values()).items():
        assert new_counts[value] >= count, value


@pytest.mark.asyncio
async def test_t2_where_precedes_limit_in_text(flag):
    flag(True)
    _repo, (_inv, selection) = await run_repo(
        "visit_summary_preferred", RULES, selection=[_doc("a", "Progress Note")]
    )
    sql = selection["sql"]
    assert sql.index("regexp_replace") < sql.index("ORDER BY") < sql.index("LIMIT")


# ---------------------------------------------------------------------------------------------
# T2b: LOINC-only docs and reset-per-call
# ---------------------------------------------------------------------------------------------
def test_t2b_loinc_only_doc_is_part_of_the_allow_term():
    include_term, loinc_term, deny_term = repo_mod._build_allowlist_predicates()
    compiled = loinc_term.compile(dialect=repo_mod.postgresql.dialect())
    sql = str(compiled)
    assert "IN (" in sql and "ILIKE" in sql.upper() and "btrim" in sql
    assert list(al.LOINC_ALLOW_CODES) in list(compiled.params.values())


@pytest.mark.asyncio
async def test_t2b_reset_per_call_discriminator_and_telemetry(flag):
    flag(True)
    # call 1: nothing selectable, one candidate that is not allowlisted -> discriminator True
    repo, stmts = await run_repo(
        "visit_summary_preferred",
        RULES,
        inventory=[(_doc("i1", "Diagnostic Imaging Study"), None)],
        selection=[],
        exists=True,
    )
    assert len(stmts) == 3 and repo.non_allowlisted_candidates_exist is True
    assert repo.visit_summary_selection["not_allowlisted_documents"] == 1
    # call 2 on the SAME repo instance: allowlisted docs present -> everything reset
    repo, stmts = await run_repo(
        "visit_summary_preferred",
        RULES,
        repo=repo,
        inventory=[(_doc("i2", "Progress Note"), None)],
        selection=[_doc("i2", "Progress Note")],
        exists=True,
    )
    assert len(stmts) == 2 and repo.non_allowlisted_candidates_exist is False
    assert repo.visit_summary_selection["not_allowlisted_documents"] == 0
    assert repo.visit_summary_selection["not_allowlisted_types"] == {}
    # call 3: another profile on the same instance wipes the visit-summary state completely
    repo, _ = await run_repo("legacy", RULES, repo=repo)
    assert (
        repo.visit_summary_selection is None
        and repo.non_allowlisted_candidates_exist is False
    )


@pytest.mark.asyncio
async def test_t2b_reset_happens_even_when_the_call_raises(flag):
    flag(True)
    repo, _ = await run_repo(
        "visit_summary_preferred",
        RULES,
        inventory=[(_doc("i1", "Lab Report"), None)],
        selection=[],
        exists=True,
    )
    assert repo.non_allowlisted_candidates_exist is True

    async def boom(*a, **k):
        raise RuntimeError("db down")

    repo.session = SimpleNamespace(execute=boom)
    with pytest.raises(RuntimeError):
        await repo.get_document_references_with_attachments(
            user_id="u",
            encounter_id="e",
            selection_profile="visit_summary_preferred",
            rule_snapshot=(RULES, {}),
        )
    assert (
        repo.non_allowlisted_candidates_exist is False
        and repo.visit_summary_selection is None
    )


# ---------------------------------------------------------------------------------------------
# T3 / T4: procedure + comprehensive callers are unaffected (BLOCKER r2-f-01 regression)
# ---------------------------------------------------------------------------------------------
def test_t3_t4_only_the_visit_summary_service_requests_the_allowlisted_profile():
    root = Path(repo_mod.__file__).resolve().parents[3] / "services" / "summarization"
    users = {
        p.name: p.read_text()
        for p in root.glob("*.py")
        if "get_document_references_with_attachments" in p.read_text()
    }
    assert set(users) == {
        "attachment_summarization.py",
        "procedure_summarization.py",
        "comprehensive_summarization.py",
    }
    assert (
        'selection_profile="visit_summary_preferred"'
        in users["attachment_summarization.py"]
    )
    assert "visit_summary_preferred" not in users["procedure_summarization.py"]
    assert "visit_summary_preferred" not in users["comprehensive_summarization.py"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile", ["legacy", "comprehensive", "procedure", "anything-else"]
)
async def test_t3_t4_flag_on_never_filters_or_probes_for_other_profiles(flag, profile):
    flag(True)
    # a procedure-style document the allowlist would reject must still be selectable
    _repo, stmts = await run_repo(
        profile,
        RULES,
        inventory=[(_doc("p1", "Anesthesia Procedure Notes"), None)],
        selection=[],
    )
    assert (
        len(stmts) == 2
    )  # empty selection but NO discriminator query for other profiles
    assert al.include_regex() not in set(stmts[1]["params"].values())
    assert al.deny_regex() not in set(stmts[1]["params"].values())


# ---------------------------------------------------------------------------------------------
# T5: discriminator + telemetry
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t5_discriminator_false_when_there_are_no_candidates_at_all(flag):
    flag(True)
    repo, stmts = await run_repo(
        "visit_summary_preferred", RULES, inventory=[], selection=[], exists=False
    )
    assert len(stmts) == 3 and repo.non_allowlisted_candidates_exist is False
    discriminator = stmts[2]
    assert "LIMIT" in discriminator["sql"]
    # base predicates + attachments + NULL-safe NOT exclude, but NO allow term and no ORDER BY
    assert (
        "regexp_replace" not in discriminator["sql"]
        and "ORDER BY" not in discriminator["sql"]
    )
    assert (
        "NOT coalesce(" in discriminator["sql"]
        and "jsonb_array_length" in discriminator["sql"]
    )


@pytest.mark.asyncio
async def test_t5_no_discriminator_query_when_selection_is_not_empty(flag):
    flag(True)
    repo, stmts = await run_repo(
        "visit_summary_preferred",
        RULES,
        selection=[_doc("a", "Progress Note")],
        exists=True,
    )
    assert len(stmts) == 2 and repo.non_allowlisted_candidates_exist is False


@pytest.mark.asyncio
async def test_t5_inventory_is_not_mutated_and_telemetry_counts_only_real_candidates(
    flag,
):
    flag(True)
    inventory = [
        (_doc("1", "Diagnostic Imaging Study"), None),  # rejected candidate
        (_doc("2", "Diagnostic Imaging Study"), None),  # rejected candidate
        (_doc("3", "Patient Instructions"), None),  # rejected candidate
        (_doc("4", "Progress Note"), None),  # allowlisted
        (
            _doc("5", "Education Note"),
            "document_type_rule:0",
        ),  # DB-excluded: not a candidate
        (
            _doc("6", "Lab Report", attachments=False),
            None,
        ),  # no attachments: not a candidate
        (_doc("7", None), None),  # NULL label, no LOINC -> rejected
        (
            _doc("8", None, code="11506-3", system="http://loinc.org"),
            None,
        ),  # LOINC-only -> allowlisted
    ]
    repo, _ = await run_repo(
        "visit_summary_preferred",
        RULES,
        inventory=inventory,
        selection=[inventory[3][0]],
    )
    tele = repo.visit_summary_selection
    assert tele["allowlist_version"] == "visit-summary-allowlist-v2"
    assert tele["not_allowlisted_documents"] == 4
    assert tele["not_allowlisted_types"] == {
        "diagnostic imaging study": 2,
        "(null)": 1,
        "patient instructions": 1,
    }
    assert repo.document_inventory["total_references"] == 8  # INVENTORY shape untouched
    assert "not_allowlisted_types" not in repo.document_inventory
    assert "allowlist_version" not in repo.document_inventory
    assert "visit_summary_selection" not in repo.document_inventory


@pytest.mark.asyncio
async def test_t5_telemetry_is_capped(flag):
    flag(True)
    inventory = [
        (_doc(str(i), f"Weird Label {i:02d} " + "x" * 80), None) for i in range(15)
    ]
    repo, _ = await run_repo(
        "visit_summary_preferred", RULES, inventory=inventory, selection=[]
    )
    tele = repo.visit_summary_selection
    assert tele["not_allowlisted_documents"] == 15
    assert len(tele["not_allowlisted_types"]) == 10
    assert all(len(k) <= 64 for k in tele["not_allowlisted_types"])
