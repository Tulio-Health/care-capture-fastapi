"""
FHIR context preparation utility for enterprise AI endpoints.

Filters FHIR resources to clinically relevant types, sorts newest-first,
caps at MAX_RESOURCES items, and truncates the serialised string to CHAR_BUDGET
characters before passing to PydanticAI agents.

Threat mitigations:
- T-02-01: 8,000-char hard truncation limits prompt injection surface.
- T-02-02: MAX_RESOURCES=50 slice applied before JSON serialisation (memory-bounded).
"""

import json
from typing import Any

# ---------------------------------------------------------------------------
# Module-level constants (exported for test assertions)
# ---------------------------------------------------------------------------

RELEVANT_RESOURCE_TYPES: set[str] = {
    "Encounter",
    "Condition",
    "MedicationRequest",
    "Procedure",
}

MAX_RESOURCES: int = 50
CHAR_BUDGET: int = 8000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_resource_date(resource: dict[str, Any]) -> str:
    """Extract the primary sort date from a FHIR resource dict.

    Returns an ISO-8601 date/datetime string for sorting.  Newer dates sort
    higher (caller uses ``reverse=True``).  Returns empty string when no date
    field is found so undated resources sink to the bottom.
    """
    resource_type = resource.get("resourceType", "")

    if resource_type == "Encounter":
        return resource.get("period", {}).get("start", "")

    if resource_type == "Condition":
        return resource.get("recordedDate", "") or resource.get("onsetDateTime", "")

    if resource_type == "MedicationRequest":
        return resource.get("authoredOn", "")

    if resource_type == "Procedure":
        return resource.get("performedDateTime", "") or resource.get(
            "performedPeriod", {}
        ).get("start", "")

    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_fhir_context(fhir_resources: list[dict[str, Any]]) -> str:
    """Prepare a compact FHIR context string for consumption by AI agents.

    Steps:
    1. Filter: keep only RELEVANT_RESOURCE_TYPES.
    2. Sort: newest resources first (descending by primary date field).
    3. Cap: take at most MAX_RESOURCES items.
    4. Serialise: json.dumps with default=str.
    5. Truncate: hard-cap at CHAR_BUDGET characters (T-02-01, T-02-02).

    Args:
        fhir_resources: Raw list of FHIR resource dicts as received from NodeAPI.

    Returns:
        A JSON string (possibly truncated) safe to embed in an AI prompt.
    """
    # Step 1 — filter to clinically relevant resource types
    filtered = [
        r
        for r in fhir_resources
        if r.get("resourceType") in RELEVANT_RESOURCE_TYPES
    ]

    # Step 2 — sort newest-first
    filtered.sort(key=_get_resource_date, reverse=True)

    # Step 3 — cap at MAX_RESOURCES
    capped = filtered[:MAX_RESOURCES]

    # Step 4 — serialise
    serialised = json.dumps(capped, default=str)

    # Step 5 — truncate to CHAR_BUDGET (T-02-01 / T-02-02 mitigations)
    return serialised[:CHAR_BUDGET]
