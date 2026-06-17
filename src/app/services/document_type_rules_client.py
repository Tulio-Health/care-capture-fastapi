"""
DocumentTypeRulesClient — Python port of the nodeAPI TypeScript client.

Fetches active document-type rules from nodeAPI's /internal/document-type-rules
endpoint with a 5-minute TTL in-process cache and a three-tier fallback ladder:

  1. Live  — cache-or-fetch from nodeAPI (happy path)
  2. Stale — last_known_good (prior successful fetch, no TTL)
  3. Floor — HARDCODED_DOCREF_EXCLUDES (15 verbatim ILIKE excludes)

PIPE-04 / D-01 through D-05.

Security note (T-04-01): the x-internal-service-key header value is NEVER
logged at any log level.
"""

import time
from typing import Optional

import httpx

from src.app.common.logging import get_logger
from src.app.core import get_settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

TTL_SECONDS: int = 300  # 5-minute TTL per D-04

# The 15 verbatim DocRef-gate exclude terms, ported from:
#   care-capture-nodeapi/src/modules/fhir-resources/constants/hardcoded-docref-excludes.ts
#
# Verbatim fidelity is load-bearing — order and spelling must match the
# TypeScript source.  matchValue holds the BARE keyword; the % wildcards are
# wrapped by the ilike predicate builder, not baked in here.
HARDCODED_DOCREF_EXCLUDES: list = [
    {
        "matchValue": "Education",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Waveform",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Consent",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Insurance",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "License",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Billing",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "HIPAA",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Reminder",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Phone Msg",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Letter",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Conversation",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Advance Directive",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Checklist",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Authorization",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
    {
        "matchValue": "Intake",
        "matchStrategy": "ilike",
        "matchTarget": "type_text",
        "action": "exclude",
        "sourceEmr": "all",
    },
]


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------


class DocumentTypeRulesClient:
    """
    In-process caching client for nodeAPI's active document-type rules.

    Cache lifecycle:
    - TTL: 5 minutes (TTL_SECONDS).  After expiry the next get_active_rules()
      re-fetches and repopulates.
    - invalidate_cache(): drops the TTL cache only; _last_known_good survives.
    - _last_known_good: updated on every successful fetch; NOT cleared by
      invalidate_cache(); serves as the stale fallback tier (D-03).
    """

    def __init__(self) -> None:
        # Cache envelope: {"rules": list[dict], "expires_at": float (monotonic)}
        self._cache: Optional[dict] = None
        # Last successfully-fetched rule set — survives invalidate_cache().
        self._last_known_good: Optional[list] = None

    async def _fetch_rules(self) -> list:
        """
        Fetch active rules from nodeAPI.

        Reads settings at call time — NOT at __init__ — so SSM parameters are
        guaranteed to be available (Pitfall 2).

        Uses a short-lived per-call httpx.AsyncClient (Pitfall 3 — no persistent
        connection to manage).

        Security (T-04-01): x-internal-service-key is NEVER logged.
        """
        settings = get_settings()
        url = f"{settings.NODE_API_URL}/internal/document-type-rules"
        headers = {"x-internal-service-key": settings.INTERNAL_SERVICE_KEY}
        params = {"activeOnly": "true"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_active_rules(self) -> list:
        """
        Return the active rule set, served from in-process cache while live.

        On cache miss or TTL expiry: fetches from nodeAPI, repopulates cache,
        updates _last_known_good (success-only).
        """
        if self._cache and time.monotonic() < self._cache["expires_at"]:
            return self._cache["rules"]

        rules = await self._fetch_rules()
        self._cache = {
            "rules": rules,
            "expires_at": time.monotonic() + TTL_SECONDS,
        }
        # Success-only update of the stale fallback tier (D-03).
        # A 200 [] is a real fetch result and is honored (D-04).
        self._last_known_good = rules
        return rules

    def invalidate_cache(self) -> None:
        """
        Clear the TTL cache (D-09).

        Lazy by design: the next get_active_rules() re-fetches.
        _last_known_good is intentionally preserved.
        """
        self._cache = None

    async def get_active_rules_with_fallback(self) -> list:
        """
        Resilient variant for callers that must never stall on a nodeAPI outage.

        Three-tier ladder (D-01):
          1. Live  — delegate to get_active_rules() (cache-or-fetch)
          2. Stale — _last_known_good if not None (prior successful fetch)
          3. Floor — HARDCODED_DOCREF_EXCLUDES (15 entries)

        Every tier drop is logged (D-05). The INTERNAL_SERVICE_KEY is never
        included in any log message (T-04-01).
        """
        try:
            return await self.get_active_rules()
        except Exception:
            if self._last_known_good is not None:
                logger.error(
                    "[DocumentTypeRulesClient] fetch failed; serving last-known-good (stale) tier"
                )
                return self._last_known_good
            else:
                logger.error(
                    "[DocumentTypeRulesClient] fetch failed; no prior fetch — serving HARDCODED floor (15 rules)"
                )
                return HARDCODED_DOCREF_EXCLUDES

    async def warm_up(self) -> None:
        """
        Startup warm-up: pre-load the active rule set so the first request is
        served from cache.

        Logs the rule count on success or a warning on failure.
        Never raises — a rules-client failure must not prevent startup (T-04-03).
        """
        try:
            rules = await self.get_active_rules()
            logger.info(
                f"[DocumentTypeRulesClient] Startup warm-up: {len(rules)} rules loaded"
            )
        except Exception:
            logger.warning(
                "[DocumentTypeRulesClient] Startup warm-up failed — using hardcoded floor (15 rules)"
            )


# ---------------------------------------------------------------------------
# Module-level lazy singleton (Pitfall 7 — created after SSM loads)
# ---------------------------------------------------------------------------

_client: Optional[DocumentTypeRulesClient] = None


def get_document_type_rules_client() -> DocumentTypeRulesClient:
    """
    Return the module-level singleton DocumentTypeRulesClient.

    Lazy construction ensures the client is created AFTER SSM parameters are
    loaded into the environment (Pitfall 7).
    """
    global _client
    if _client is None:
        _client = DocumentTypeRulesClient()
    return _client
