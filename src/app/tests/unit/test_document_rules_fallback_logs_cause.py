"""Regression test: the rules-client must log WHY a live fetch failed, not just that it fell back.

Background (dev incident): `document_type_rules_client` served the hardcoded `floor` tier for
100% of resolutions during a full sync run. The only evidence in CloudWatch was a wall of

    WARNING - Document rules using floor fallback

plus the escalating "N consecutive non-live resolutions" warning. Neither line carried the
underlying exception, so a reader could not tell a connect timeout from a 401, a 404, a 500 or a
JSON parse error -- every one of those failure modes produced byte-identical logs. The actual
cause (nodeapi's root-mounted /internal/document-type-rules hanging until our 10s httpx timeout,
because a global Nest cache interceptor never resolved its cache lookup) was completely invisible
from the fastapi side and had to be found by probing nodeapi directly.

These tests pin the fix: the fallback warning now includes the exception type and message, for
both the per-resolution path and the startup warm-up path.

Security (T-04-01): the x-internal-service-key must still never appear in any log record. httpx
exception reprs carry the request URL but never request headers, so including `exc` is safe --
the final test asserts this explicitly with a key planted in settings.
"""

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.app.services.document_type_rules_client import (
    HARDCODED_DOCREF_EXCLUDES,
    DocumentTypeRulesClient,
)

SECRET_KEY = "super-secret-internal-service-key-value"


def _messages(caplog) -> str:
    """All formatted log messages from the client, joined."""
    return "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_floor_fallback_logs_underlying_timeout(caplog):
    """A hanging nodeapi (the real incident) must be identifiable from the log line alone."""
    client = DocumentTypeRulesClient()
    boom = httpx.ReadTimeout("timed out", request=None)

    with patch.object(client, "_fetch_rules", AsyncMock(side_effect=boom)):
        with caplog.at_level(logging.WARNING):
            rules, provenance = await client.resolve_rules()

    # Ladder still behaves: no prior success -> floor.
    assert provenance["tier"] == "floor"
    assert rules == list(HARDCODED_DOCREF_EXCLUDES)

    text = _messages(caplog)
    assert "floor" in text
    # The regression this test exists for: the CAUSE must be present.
    assert "ReadTimeout" in text, f"exception type missing from log: {text!r}"
    assert "timed out" in text, f"exception message missing from log: {text!r}"


@pytest.mark.asyncio
async def test_stale_fallback_logs_underlying_http_status(caplog):
    """An auth/routing regression (401/404) must be distinguishable from a timeout."""
    client = DocumentTypeRulesClient()
    good = [{"matchValue": "Depart Summary", "action": "prefer"}]

    # One successful fetch first, so the ladder has a last-known-good to drop to.
    with patch.object(client, "_fetch_rules", AsyncMock(return_value=good)):
        assert await client.get_active_rules() == good

    client.invalidate_cache()
    response = httpx.Response(401, request=httpx.Request("GET", "https://node/internal/x"))
    boom = httpx.HTTPStatusError("401 Unauthorized", request=response.request, response=response)

    with patch.object(client, "_fetch_rules", AsyncMock(side_effect=boom)):
        with caplog.at_level(logging.WARNING):
            rules, provenance = await client.resolve_rules()

    assert provenance["tier"] == "stale"
    assert rules == good

    text = _messages(caplog)
    assert "stale" in text
    assert "HTTPStatusError" in text, f"exception type missing from log: {text!r}"
    assert "401" in text, f"status missing from log: {text!r}"


@pytest.mark.asyncio
async def test_warm_up_failure_logs_cause(caplog):
    """Startup warm-up swallowed its cause too -- same blind spot, same fix."""
    client = DocumentTypeRulesClient()
    boom = httpx.ConnectError("All connection attempts failed")

    with patch.object(client, "_fetch_rules", AsyncMock(side_effect=boom)):
        with caplog.at_level(logging.WARNING):
            await client.warm_up()  # must never raise (T-04-03)

    text = _messages(caplog)
    assert "warm-up failed" in text.lower()
    assert "ConnectError" in text, f"exception type missing from log: {text!r}"


@pytest.mark.asyncio
async def test_internal_service_key_is_never_logged(caplog):
    """T-04-01 still holds: widening the log must not leak the shared secret."""
    client = DocumentTypeRulesClient()

    class _Settings:
        NODE_API_URL = "https://node-api.example.com"
        INTERNAL_SERVICE_KEY = SECRET_KEY

    # Let the REAL _fetch_rules run (so the key is genuinely in play) against a
    # transport that always fails -- the failure is what gets logged.
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    with patch(
        "src.app.services.document_type_rules_client.get_settings",
        return_value=_Settings(),
    ), patch(
        "httpx.AsyncClient",
        lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(_boom)),
    ):
        with caplog.at_level(logging.DEBUG):
            _, provenance = await client.resolve_rules()

    assert provenance["tier"] == "floor"
    assert SECRET_KEY not in _messages(caplog)
    assert SECRET_KEY not in caplog.text
