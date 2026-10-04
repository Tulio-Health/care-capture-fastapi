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

import threading
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
# F6 (round9-revision3.md F6): documentClass passthrough needs NO code change here --
# _fetch_rules() below returns response.json() verbatim with zero field allowlisting,
# so a documentClass key added server-side (nodeapi N1/N2, out of this fastapi-only
# PR's scope) already reaches _build_prefer_predicates (fhir_resources.py, F2) the
# moment nodeapi starts sending it, the same way resolvedType/action already do.
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
        # F6 (round9-revision3.md S3.8 / risk R7): consecutive-stale-serve counter. Fix
        # 1's preference ordering is a silent no-op whenever this channel serves a
        # resolved-rule snapshot that predates the curated prefer rules, so a run of
        # stale/floor serves needs to be LOUDER than the existing per-call
        # "Document rules using stale fallback" warning (easy to miss in a 96-line
        # burst, as the stress run that motivated this fix demonstrated).
        self._consecutive_non_live_serves: int = 0

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
        return (await self.resolve_rules())[0]

    # F6: fires a louder warning once a run of consecutive non-live serves reaches this
    # length, on top of the existing per-call "stale fallback" warning. Tunable.
    _STALE_STREAK_ALERT_THRESHOLD: int = 10

    async def resolve_rules(self):
        """Return a rule set and the provenance of that exact resolution."""
        import hashlib
        import json
        try:
            rules = await self.get_active_rules()
            tier = "live"
            self._consecutive_non_live_serves = 0
        except Exception as exc:
            if self._last_known_good is not None:
                rules = self._last_known_good
                tier = "stale"
            else:
                rules = list(HARDCODED_DOCREF_EXCLUDES)
                tier = "floor"
            # Log the UNDERLYING failure, not just the fallback decision. Previously this
            # logged only "Document rules using floor fallback", which told an operator
            # that the ladder dropped but not why -- a 100%-floor outage was
            # indistinguishable from a timeout, a 401, a 404 or a parse error, and the
            # real cause (nodeapi hanging until our 10s httpx timeout) was invisible in
            # CloudWatch. httpx exception reprs carry the URL but never request headers,
            # so the x-internal-service-key is still never logged (T-04-01).
            logger.warning(
                "Document rules using %s fallback -- live fetch failed: %s: %s",
                tier,
                type(exc).__name__,
                exc,
            )
            self._consecutive_non_live_serves += 1
            if self._consecutive_non_live_serves == self._STALE_STREAK_ALERT_THRESHOLD or (
                self._consecutive_non_live_serves > self._STALE_STREAK_ALERT_THRESHOLD
                and self._consecutive_non_live_serves % self._STALE_STREAK_ALERT_THRESHOLD == 0
            ):
                # F6 (round9-revision3.md S3.8 / risk R7): a streak this long means any
                # curated 'prefer' rules shipped by Fix 1 are very likely invisible to
                # fastapi right now -- Fix 1 degrades to a silent no-op, not a crash, so
                # this is the signal an operator needs to notice that on their own.
                logger.warning(
                    "Document rules client has served %d consecutive non-live "
                    "(stale/floor) resolutions -- curated prefer/exclude rule changes "
                    "may not be reaching fastapi.",
                    self._consecutive_non_live_serves,
                )
        digest = hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return rules, {"tier": tier, "digest": digest}

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
        except Exception as exc:
            # WR-06: accurate message — floor is not loaded here; it will be served
            # on-demand when get_active_rules_with_fallback() is first called.
            # The cause is included for the same reason as in resolve_rules(): a
            # bare "warm-up failed" line cannot be triaged. Key is never logged.
            logger.warning(
                "[DocumentTypeRulesClient] Startup warm-up failed (%s: %s) — "
                "floor rules will be served on-demand when first request arrives (15 rules)",
                type(exc).__name__,
                exc,
            )


# ---------------------------------------------------------------------------
# Module-level lazy singleton (Pitfall 7 — created after SSM loads)
# CR-04: double-checked locking ensures thread-safe singleton construction.
# ---------------------------------------------------------------------------

_client: Optional[DocumentTypeRulesClient] = None
_client_lock = threading.Lock()


def get_document_type_rules_client() -> DocumentTypeRulesClient:
    """
    Return the module-level singleton DocumentTypeRulesClient.

    Lazy construction ensures the client is created AFTER SSM parameters are
    loaded into the environment (Pitfall 7).

    Thread-safe via double-checked locking (CR-04): two concurrent callers
    (e.g. lifespan warm_up() and an early request) can no longer each
    construct a separate instance with an independent cache.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = DocumentTypeRulesClient()
    return _client
