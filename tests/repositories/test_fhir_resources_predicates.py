"""
Unit tests for _build_exclude_predicates() in fhir_resources.py.

Tests focus on the module-level predicate builder only — no DB session required.

Tests:
  1 - ilike rule produces one ilike clause
  2 - exact rule produces one equality clause
  3 - regex rule produces one regex clause
  4 - loinc_code rule is skipped (D-09)
  5 - include rule is skipped (D-07)
  6 - empty rules list returns empty list
  7 - HARDCODED_DOCREF_EXCLUDES produces exactly 15 predicates
  8 - unknown matchStrategy is skipped defensively
"""

import pytest

from src.app.db.objects.repositories.fhir_resources import _build_exclude_predicates
from src.app.services.document_type_rules_client import HARDCODED_DOCREF_EXCLUDES


# ---------------------------------------------------------------------------
# Test 1 — ilike rule produces one ilike clause
# ---------------------------------------------------------------------------

def test_ilike_rule_produces_one_clause():
    rules = [
        {
            "action": "exclude",
            "matchStrategy": "ilike",
            "matchTarget": "type_text",
            "matchValue": "Education",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert len(result) == 1
    # SQLAlchemy renders ilike() as "lower(col) LIKE lower(val)" in str()
    clause_str = str(result[0]).lower()
    assert "like" in clause_str


# ---------------------------------------------------------------------------
# Test 2 — exact rule produces one equality clause
# ---------------------------------------------------------------------------

def test_exact_rule_produces_equality_clause():
    rules = [
        {
            "action": "exclude",
            "matchStrategy": "exact",
            "matchTarget": "type_text",
            "matchValue": "SomeType",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert len(result) == 1
    # Equality operator — str() should contain "=" but not "LIKE"
    clause_str = str(result[0]).lower()
    assert "like" not in clause_str


# ---------------------------------------------------------------------------
# Test 3 — regex rule produces one clause
# ---------------------------------------------------------------------------

def test_regex_rule_produces_one_clause():
    rules = [
        {
            "action": "exclude",
            "matchStrategy": "regex",
            "matchTarget": "type_text",
            "matchValue": "^Edu",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Test 4 — loinc_code rule is skipped (D-09)
# ---------------------------------------------------------------------------

def test_loinc_code_rule_skipped():
    rules = [
        {
            "action": "exclude",
            "matchStrategy": "exact",
            "matchTarget": "loinc_code",
            "matchValue": "12345-6",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert result == []


# ---------------------------------------------------------------------------
# Test 5 — include rule is skipped (D-07)
# ---------------------------------------------------------------------------

def test_include_rule_skipped():
    rules = [
        {
            "action": "include",
            "matchStrategy": "ilike",
            "matchTarget": "type_text",
            "matchValue": "Note",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert result == []


# ---------------------------------------------------------------------------
# Test 6 — empty rules list returns empty list
# ---------------------------------------------------------------------------

def test_empty_rules_returns_empty_list():
    result = _build_exclude_predicates([])
    assert result == []


# ---------------------------------------------------------------------------
# Test 7 — HARDCODED_DOCREF_EXCLUDES produces exactly 15 predicates
# ---------------------------------------------------------------------------

def test_hardcoded_excludes_produces_15_predicates():
    result = _build_exclude_predicates(HARDCODED_DOCREF_EXCLUDES)
    assert len(result) == 15


# ---------------------------------------------------------------------------
# Test 8 — unknown matchStrategy is skipped defensively
# ---------------------------------------------------------------------------

def test_unknown_strategy_skipped():
    rules = [
        {
            "action": "exclude",
            "matchStrategy": "fuzzy",
            "matchTarget": "type_text",
            "matchValue": "X",
        }
    ]
    result = _build_exclude_predicates(rules)
    assert result == []
