"""
Wave 0 stubs — tests are intentionally failing until implementation plans complete.

Covers: SIG-02 — FHIR context preparation for signal computation and profile building.
"""

import json
import pytest

# This import will fail (ImportError) until fhir_prep.py is created — that is the intended red state.
from src.app.services.enterprise.fhir_prep import prepare_fhir_context


def _make_encounter(date: str, idx: int = 0) -> dict:
    """Helper: build a minimal FHIR Encounter resource with a period start date."""
    return {
        "resourceType": "Encounter",
        "id": f"enc-{idx}",
        "period": {"start": date},
    }


def test_returns_at_most_50_resources():
    """prepare_fhir_context with 100 Encounter resources returns at most 50."""
    resources = [_make_encounter("2024-01-01", i) for i in range(100)]
    result = prepare_fhir_context(resources)
    parsed = json.loads(result)
    assert len(parsed) <= 50


def test_truncates_to_8000_chars():
    """prepare_fhir_context with large resources returns at most 8000 chars."""
    # Each resource ~1500 chars when serialised
    large_resource = {
        "resourceType": "Encounter",
        "id": "big",
        "period": {"start": "2024-01-01"},
        "note": [{"text": "x" * 1400}],
    }
    resources = [dict(large_resource, id=f"big-{i}") for i in range(8)]
    result = prepare_fhir_context(resources)
    assert len(result) <= 8000


def test_filters_irrelevant_types():
    """prepare_fhir_context removes AllergyIntolerance (and other non-relevant) resources."""
    resources = [
        _make_encounter("2024-06-01", 0),
        {"resourceType": "AllergyIntolerance", "id": "allergy-1"},
        {"resourceType": "Observation", "id": "obs-1"},
    ]
    result = prepare_fhir_context(resources)
    parsed = json.loads(result)
    resource_types = {r.get("resourceType") for r in parsed}
    assert "AllergyIntolerance" not in resource_types
    assert "Observation" not in resource_types
    assert "Encounter" in resource_types


def test_sorts_newest_first():
    """Newest resources appear first in the output (descending by date)."""
    resources = [
        _make_encounter("2024-01-01", 0),
        _make_encounter("2026-01-01", 1),
        _make_encounter("2020-05-15", 2),
    ]
    result = prepare_fhir_context(resources)
    parsed = json.loads(result)
    dates = [r.get("period", {}).get("start", "") for r in parsed]
    assert dates[0] == "2026-01-01", f"Expected newest first, got {dates}"
