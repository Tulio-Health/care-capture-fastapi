"""T0 / T0c / sql_in_sync -- the visit-summary allowlist (v2) constant and its SQL twin."""
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.app.services import visit_summary_allowlist as al
from src.app.tests.unit.visit_summary_allowlist_labels import DEV_LABELS, LABEL_TABLE, PROD_LABELS
from src.app.tests.unit.visit_summary_allowlist_probes import P

REPO_ROOT = Path(__file__).resolve().parents[4]
CENSUS_SQL = REPO_ROOT / "scripts" / "sql" / "visit_summary_allowlist_census.sql"
RENDERER = REPO_ROOT / "scripts" / "render_visit_summary_allowlist_sql.py"

LOINC = "http://loinc.org"


# ---------------------------------------------------------------------------------------------
# shape of the shipped constant
# ---------------------------------------------------------------------------------------------
def test_constant_shape_and_identity():
    assert al.ALLOWLIST_VERSION == "visit-summary-allowlist-v2"
    kinds = [r[1] for r in al.VISIT_SUMMARY_ALLOWLIST]
    assert len(kinds) == 38 and kinds.count("include") == 25 and kinds.count("deny") == 13
    assert len({r[0] for r in al.VISIT_SUMMARY_ALLOWLIST}) == 38
    assert al.LOINC_ALLOW_CODES == (
        "11506-3", "34117-2", "11488-4", "34111-5", "18842-5", "34133-9", "34748-4", "28570-0", "11504-8",
    )
    # the three result codes and the nurse telephone code are deliberately NOT allowed
    assert not {"18748-4", "11502-2", "11526-1", "34139-6"} & set(al.LOINC_ALLOW_CODES)
    # byte identity with the round-5 census constant
    assert al.canonical_sha() == "b317965cf691a0a8e2779faf8f30cd4707b60eb5600ada2a4250907b1cf5e726"


# ---------------------------------------------------------------------------------------------
# T0: probes + label tables
# ---------------------------------------------------------------------------------------------
def test_probe_count():
    assert len(P) == 113


@pytest.mark.parametrize("label,expected", P, ids=[repr(p[0]) for p in P])
def test_probe(label, expected):
    assert al.match(label)[0] is bool(expected)


def test_label_table_sizes():
    assert len(DEV_LABELS) == 108
    assert len(PROD_LABELS) >= 50
    assert len(LABEL_TABLE) == len(DEV_LABELS) + len(PROD_LABELS)


@pytest.mark.parametrize("env,label,eligible,inc_rule,deny_rule", LABEL_TABLE, ids=[f"{r[0]}:{r[1]}" for r in LABEL_TABLE])
def test_label_table(env, label, eligible, inc_rule, deny_rule):
    got_eligible, got_inc, got_deny = al.match(label)
    assert (got_eligible, got_inc, got_deny) == (eligible, inc_rule, deny_rule)


@pytest.mark.parametrize(
    "variant",
    ["Progress\u00a0Note", "  PROGRESS   NOTE ", "progress\tnote", "Progress\r\nNote", "PROGRESS NOTE\u00a0"],
)
def test_whitespace_and_case_variants_fold(variant):
    assert al.match(variant) == (True, "note.progress", None)


def test_normalize_label():
    assert al.normalize_label(None) == ""
    assert al.normalize_label("\u00a0H\u00a0&\u00a0P\t") == "h & p"


# ---------------------------------------------------------------------------------------------
# LOINC fallback
# ---------------------------------------------------------------------------------------------
def test_loinc_only_null_label_is_eligible():
    assert al.match(None, "11506-3", LOINC) == (True, "loinc:11506-3", None)
    assert al.match("", "34133-9", "urn:oid:2.16.840.1.113883.6.1") == (True, "loinc:34133-9", None)
    assert al.match(None, "34748-4", " http://LOINC.org ") == (True, "loinc:34748-4", None)


def test_loinc_oid_matches_only_exactly():
    assert al.match(None, "11506-3", al.LOINC_OID)[0] is True
    assert al.match(None, "11506-3", al.LOINC_OID + ".1")[0] is False


def test_epic_oid_systems_are_not_loinc():
    assert al.match(None, "11506-3", "urn:oid:1.2.840.114350.1.13.0.1.7.2.688879")[0] is False


def test_code_without_system_or_unknown_code_is_ineligible():
    assert al.match(None, "11506-3", None)[0] is False
    assert al.match(None, "11506-3", "")[0] is False
    assert al.match(None, "99999-9", LOINC)[0] is False
    assert al.match(None, "11502-2", LOINC)[0] is False  # lab report code is deliberately not allowed
    assert al.match(None, None, LOINC)[0] is False


def test_deny_wins_over_loinc_code():
    eligible, inc, deny = al.match("Patient Instructions", "11506-3", LOINC)
    assert eligible is False and deny == "deny.instructions" and inc == "loinc:11506-3"


def test_label_include_and_loinc_both_present_keeps_label_rule():
    assert al.match("Progress Note", "11506-3", LOINC) == (True, "note.progress", None)


def test_label_telemetry_key():
    assert al.label_telemetry_key(None) == "(null)"
    assert al.label_telemetry_key("  ") == "(null)"
    assert al.label_telemetry_key("X" * 100) == "x" * 64


# ---------------------------------------------------------------------------------------------
# T0c portability: both engines (Python re / PostgreSQL ARE) must read every pattern the same way
# ---------------------------------------------------------------------------------------------
PORTABLE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789 &/()|?+^$[]-\u2013\u2014")


@pytest.mark.parametrize("rule_id,kind,pattern,reason", al.VISIT_SUMMARY_ALLOWLIST, ids=[r[0] for r in al.VISIT_SUMMARY_ALLOWLIST])
def test_pattern_is_portable(rule_id, kind, pattern, reason):
    assert "\\" not in pattern, "backslash escapes differ between Python re and PostgreSQL ARE"
    assert set(pattern) <= PORTABLE_CHARS, sorted(set(pattern) - PORTABLE_CHARS)
    assert pattern == pattern.lower()
    re.compile(pattern)
    assert kind in {"include", "deny"}


def test_combined_alternations_agree_with_per_rule_matching():
    inc, den = re.compile(al.include_regex()), re.compile(al.deny_regex())
    for label, _expected in P:
        lbl = al.normalize_label(label)
        eligible, inc_rule, deny_rule = al.match(label)
        assert bool(lbl and inc.search(lbl)) is (inc_rule is not None and not inc_rule.startswith("loinc:"))
        assert bool(lbl and den.search(lbl)) is (deny_rule is not None)


# ---------------------------------------------------------------------------------------------
# sql_in_sync: the checked-in census SQL is byte-for-byte the re-render of the constant
# ---------------------------------------------------------------------------------------------
def _load_renderer():
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_visit_summary_allowlist_sql", RENDERER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_visit_summary_allowlist_sql_in_sync():
    rendered = _load_renderer().render_file()
    on_disk = CENSUS_SQL.read_bytes()
    assert rendered == on_disk, "census SQL is stale: run scripts/render_visit_summary_allowlist_sql.py --write"


def test_census_sql_is_utf8_with_nbsp_whitespace_class_in_every_generated_block():
    raw = CENSUS_SQL.read_bytes()
    text = raw.decode("utf-8")
    blocks = re.findall(r"-- BEGIN GENERATED ALLOWLIST.*?-- END GENERATED ALLOWLIST", text, re.S)
    assert len(blocks) == 14
    assert all(b == al.render_allowlist_sql() for b in blocks)
    assert "\u00a0" in text  # NBSP literal in the whitespace class, not an escape
    assert len(text.splitlines()) == 2091


def test_renderer_check_cli_passes():
    result = subprocess.run([sys.executable, str(RENDERER), "--check"], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------------------------
# startup log
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("false", "False"), ("true", "True")])
def test_startup_log_reports_flag_and_version(monkeypatch, caplog, raw, expected):
    from src.app.config.configuration_summary import log_visit_summary_allowlist_configuration
    from src.app.core.settings import reset_settings

    monkeypatch.setenv("VISIT_SUMMARY_ALLOWLIST_ENABLED", raw)
    reset_settings()
    try:
        with caplog.at_level(logging.INFO):
            log_visit_summary_allowlist_configuration()
    finally:
        monkeypatch.delenv("VISIT_SUMMARY_ALLOWLIST_ENABLED", raising=False)
        reset_settings()
    assert f"visit_summary_allowlist enabled={expected} version=visit-summary-allowlist-v2" in caplog.text
