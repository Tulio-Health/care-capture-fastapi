"""
Unit tests for DocumentTypeRulesClient.

Tests:
  1  - cache hit: second call within TTL returns cached result (no HTTP)
  2  - TTL expiry: expired cache triggers a new HTTP call
  3  - fallback to last_known_good when HTTP fails
  4  - fallback to hardcoded floor when HTTP fails and no prior fetch
  5  - warm_up success: no exception + _last_known_good populated
  6  - warm_up failure: no exception raised on HTTP error
  7  - invalidate_cache: clears _cache but preserves _last_known_good
  8  - HARDCODED_DOCREF_EXCLUDES has exactly 15 entries
  9  - HARDCODED_DOCREF_EXCLUDES contains all 15 expected keywords
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.app.services.document_type_rules_client import (
    DocumentTypeRulesClient,
    HARDCODED_DOCREF_EXCLUDES,
    get_document_type_rules_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rules(count: int = 3) -> list:
    return [
        {"matchValue": f"Rule{i}", "matchStrategy": "ilike", "matchTarget": "type_text",
         "action": "exclude", "sourceEmr": "all"}
        for i in range(count)
    ]


def _mock_response(rules: list):
    """Build a mock httpx Response-like object."""
    resp = MagicMock()
    resp.json.return_value = rules
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Test 1 — cache hit: HTTP called exactly once for two consecutive calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit():
    client = DocumentTypeRulesClient()
    rules = make_rules(3)

    mock_resp = _mock_response(rules)
    mock_http = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = mock_http
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result1 = await client.get_active_rules()
        result2 = await client.get_active_rules()

    assert result1 == rules
    assert result2 == rules
    # HTTP should only have been called once (second call served from cache)
    assert mock_http.call_count == 1


# ---------------------------------------------------------------------------
# Test 2 — TTL expiry: expired cache triggers a new HTTP call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ttl_expiry():
    client = DocumentTypeRulesClient()
    rules = make_rules(2)

    # Pre-populate cache with an already-expired timestamp
    client._cache = {
        "rules": rules,
        "expires_at": time.monotonic() - 1.0,  # 1 second in the past
    }
    client._last_known_good = rules

    mock_resp = _mock_response(rules)
    mock_http = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = mock_http
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.get_active_rules()

    assert result == rules
    assert mock_http.call_count == 1  # Re-fetched due to expired TTL


# ---------------------------------------------------------------------------
# Test 3 — fallback to last_known_good when HTTP fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_to_last_known_good():
    client = DocumentTypeRulesClient()
    prior_rules = make_rules(4)
    client._last_known_good = prior_rules

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.get_active_rules_with_fallback()

    assert result == prior_rules
    assert result is not HARDCODED_DOCREF_EXCLUDES


# ---------------------------------------------------------------------------
# Test 4 — fallback to hardcoded floor when HTTP fails and no prior fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_to_hardcoded_floor():
    client = DocumentTypeRulesClient()
    assert client._last_known_good is None

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=Exception("Timeout"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.get_active_rules_with_fallback()

    assert result == HARDCODED_DOCREF_EXCLUDES
    assert len(result) == 15


# ---------------------------------------------------------------------------
# Test 5 — warm_up success: no exception + _last_known_good populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_warm_up_success():
    client = DocumentTypeRulesClient()
    rules = make_rules(5)

    mock_resp = _mock_response(rules)

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        # Must not raise
        await client.warm_up()

    assert client._last_known_good == rules


# ---------------------------------------------------------------------------
# Test 6 — warm_up failure: no exception raised
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_warm_up_failure_does_not_raise():
    client = DocumentTypeRulesClient()

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=Exception("Network error"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        # Must not raise
        await client.warm_up()

    # _last_known_good stays None (no successful fetch)
    assert client._last_known_good is None


# ---------------------------------------------------------------------------
# Test 7 — invalidate_cache: clears _cache but preserves _last_known_good
# ---------------------------------------------------------------------------

def test_invalidate_cache_preserves_last_known_good():
    client = DocumentTypeRulesClient()
    rules = make_rules(2)
    client._cache = {"rules": rules, "expires_at": time.monotonic() + 300}
    client._last_known_good = rules

    client.invalidate_cache()

    assert client._cache is None
    assert client._last_known_good == rules  # must NOT be cleared


# ---------------------------------------------------------------------------
# Test 8 — HARDCODED_DOCREF_EXCLUDES has exactly 15 entries
# ---------------------------------------------------------------------------

def test_hardcoded_excludes_length():
    assert len(HARDCODED_DOCREF_EXCLUDES) == 15


# ---------------------------------------------------------------------------
# Test 9 — HARDCODED_DOCREF_EXCLUDES contains all 15 expected keywords
# ---------------------------------------------------------------------------

EXPECTED_KEYWORDS = [
    "Education", "Waveform", "Consent", "Insurance", "License",
    "Billing", "HIPAA", "Reminder", "Phone Msg", "Letter",
    "Conversation", "Advance Directive", "Checklist", "Authorization", "Intake",
]


def test_hardcoded_excludes_keywords():
    match_values = {entry["matchValue"] for entry in HARDCODED_DOCREF_EXCLUDES}
    for keyword in EXPECTED_KEYWORDS:
        assert keyword in match_values, f"Missing keyword: {keyword}"

    # Also verify every entry has the correct shape
    for entry in HARDCODED_DOCREF_EXCLUDES:
        assert entry["matchStrategy"] == "ilike"
        assert entry["matchTarget"] == "type_text"
        assert entry["action"] == "exclude"
        assert entry["sourceEmr"] == "all"
