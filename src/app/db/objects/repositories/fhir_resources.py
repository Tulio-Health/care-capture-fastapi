import re
from uuid import UUID

from sqlalchemy import String, and_, cast, func, literal_column, or_, select, true
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.common.logging import get_logger
from src.app.core.settings import get_settings
from src.app.db.models.fhir_resources import FhirResource
from src.app.services import visit_summary_allowlist as allowlist
from src.app.services.document_type_rules_client import (
    HARDCODED_DOCREF_EXCLUDES,
    get_document_type_rules_client,
)

logger = get_logger(__name__)

# Sized by the round9-revision3.md S10 step-4b live-dev runtime measurement, 2026-10-02
# (fastapi-app-v2-dev @ 943f66c, nodejs-app-v2-dev @ ced25e47).
#
# Regime that actually governed the measurement: SYNC / 110 s -- NOT the 300 s async path
# round9-revision3.md expected. fix/async-summary-quickfix is not an ancestor of either
# deployed branch, the deployed fastapi tree has no async dispatch path, and the deployed
# nodeapi sends timeout_seconds: 110 (conversation-summary.service.ts:271,:455), so SSM
# /tuliohealth/dev/summary/async_mode="async" is inert. Headroom target was therefore the
# sync one: >=30% of 110 s, i.e. <=77 s.
#
# Measurement (encounter 97954819, appointment f5b7474f-2088-4bda-af66-4a47838c4654):
# 69 documents / 5.04 MB ingested end-to-end in 58.3 s of in-process budget wall clock
# (budget.job_end wall_seconds=58.311, 60.27 s client wall), outcome `partial`,
# validation passed, model_call_headroom=48 of 64 -- extraction time, not the model-call
# budget, is what the cap actually buys back. That is 47% headroom at 69 documents.
# Extrapolating the same per-document cost to 100 documents gives ~84.5 s = 23% headroom,
# which FAILS the >=30% rule, so 100 could not be left in place.
#
# 50 is set below the largest workload measured to fit (69) to keep ~2x the required
# margin: ~42 s projected at the measured per-document rate (~62% headroom). The extra
# margin is deliberate -- dev's Cerner-sandbox corpus is smaller per document than real
# production documents, and 20 of the 69 documents in the measured run took the slower
# OCR_REQUIRED path.
#
# Must move together with document_ingestion.MAX_DOCUMENTS (F7c) -- that constant is the
# real binding cap (attachment-counted); this one only has to supply enough
# DocumentReferences that the binding cap can actually trip.
DOCUMENT_SELECTION_CAP = 50


def _build_exclude_predicates(rules: list) -> list:
    """
    Build a list of SQLAlchemy WHERE predicates from document-type exclude rules.

    Rules processing (PIPE-05):
    - Only rules with action="exclude" are processed (D-07: include rules are inert).
    - Rules with matchTarget="loinc_code" are skipped (D-09: no LOINC support in FastAPI).
    - Supported matchStrategy values: "ilike", "exact", "regex".
    - Unknown strategies are silently skipped (defensive default).

    If the returned list is empty (no exclude rules), the caller should treat
    this as a no-op (qualify-all behavior, consistent with D-04).

    Args:
        rules: List of document-type rule dicts (matchValue, matchStrategy,
               matchTarget, action, sourceEmr).

    Returns:
        List of SQLAlchemy column expressions, one per applicable exclude rule.
    """
    clauses = []
    type_col = FhirResource.data["type"].astext

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        count_before = len(clauses)
        # D-07: only exclude rules
        if rule.get("action") != "exclude":
            continue

        # D-09: skip loinc_code rules — no LOINC field path established in FastAPI
        if rule.get("matchTarget") == "loinc_code":
            continue

        value = rule.get("matchValue", "")
        strategy = rule.get("matchStrategy", "ilike")

        if strategy == "ilike":
            clauses.append(type_col.ilike(f"%{value}%"))
        elif strategy == "exact":
            clauses.append(type_col == value)
        elif strategy == "regex":
            # CR-03: guard against ReDoS and invalid POSIX regex values.
            # An oversized or malformed pattern would stall or crash the PostgreSQL
            # regex engine, or raise an unhandled 500 on every affected request.
            if not value or len(value) > 200:
                logger.warning(
                    "[_build_exclude_predicates] skipping regex rule — "
                    "value absent or exceeds 200 chars"
                )
                continue
            try:
                re.compile(value)  # POSIX-compatible syntax pre-check
            except re.error as exc:
                logger.warning(
                    f"[_build_exclude_predicates] skipping invalid regex rule value: {exc}"
                )
                continue
            clauses.append(type_col.op("~")(value))
        if len(clauses) > count_before and rule.get("sourceEmr") not in (None, "", "all", "ALL", "*"):
            source = str(rule["sourceEmr"]).upper()
            clauses[-1] = and_(clauses[-1], cast(FhirResource.ehr_provider, String) == source)
        # unknown strategy: skip silently (defensive)

    return clauses


def _build_allowlist_predicates(data_col=None) -> tuple:
    """
    SQL twin of ``visit_summary_allowlist.match`` over a ``fhir_resources.data`` JSONB column.

    Returns ``(include_term, loinc_term, deny_term)``, each a boolean expression that is NEVER
    NULL (coalesced to false), so ``(include OR loinc) AND NOT deny`` is a plain two-valued
    filter and a document with a NULL/missing type simply fails the label terms:

    * include_term: ``lbl ~ <alternation of the 25 include patterns>``
    * loinc_term:   ``typeCode IN (<LOINC_ALLOW_CODES>) AND (typeSystem ILIKE '%loinc%' OR
                    btrim(typeSystem) = <LOINC OID>)``
    * deny_term:    ``lbl ~ <alternation of the 13 deny patterns>``

    where ``lbl = lower(btrim(regexp_replace(data->>'type', <WS class incl. NBSP>, ' ', 'g')))``.
    Patterns are bound as parameters (never inlined). The real-PostgreSQL parity test
    (``src/app/tests/pg_parity``) pins these expressions against ``match()``.
    """
    data = FhirResource.data if data_col is None else data_col
    label = func.lower(
        func.btrim(
            func.regexp_replace(
                func.jsonb_extract_path_text(data, "type"),
                allowlist.WS_CLASS_SQL,
                " ",
                "g",
            )
        )
    )
    code = func.jsonb_extract_path_text(data, "typeCode")
    system = func.jsonb_extract_path_text(data, "typeSystem")
    include_term = func.coalesce(label.op("~")(allowlist.include_regex()), False)
    loinc_term = func.coalesce(
        and_(
            code.in_(allowlist.LOINC_ALLOW_CODES),
            or_(
                system.ilike("%" + allowlist.LOINC_SYSTEM_PATTERN + "%"),
                func.btrim(system) == allowlist.LOINC_OID,
            ),
        ),
        False,
    )
    deny_term = func.coalesce(label.op("~")(allowlist.deny_regex()), False)
    return include_term, loinc_term, deny_term


ALLOWLIST_TELEMETRY_TOP_TYPES = 10
ALLOWLIST_TELEMETRY_LABEL_MAX = 64


def _has_attachments(data) -> bool:
    attachments = data.get("attachments") if isinstance(data, dict) else None
    return isinstance(attachments, list) and len(attachments) > 0


def _allowlist_telemetry(inventory) -> dict:
    """Capped telemetry about candidate documents the allowlist rejects.

    Candidates are INVENTORY rows that the SELECTION query could otherwise return: attachments
    present and not excluded by a DB/floor rule (``reason is None``). ``match`` is the same
    matcher the SQL term is parity-tested against. Output is bounded (top 10 labels, labels
    <= 64 chars, "(null)" for empty) and holds generic document-type labels only.
    """
    counts: dict = {}
    dropped = 0
    for resource, reason in inventory:
        data = getattr(resource, "data", None) or {}
        if reason is not None or not _has_attachments(data):
            continue
        eligible, _inc, _deny = allowlist.match(data.get("type"), data.get("typeCode"), data.get("typeSystem"))
        if eligible:
            continue
        dropped += 1
        key = allowlist.label_telemetry_key(data.get("type"), ALLOWLIST_TELEMETRY_LABEL_MAX)
        counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:ALLOWLIST_TELEMETRY_TOP_TYPES]
    return {
        "allowlist_version": allowlist.ALLOWLIST_VERSION,
        "not_allowlisted_documents": dropped,
        "not_allowlisted_types": dict(top),
    }


def _build_prefer_predicates(rules: list) -> list:
    """
    Build a list of SQLAlchemy WHERE predicates from document-type prefer rules.

    Mirrors `_build_exclude_predicates`'s matching logic (D-09 loinc skip, ilike/exact/
    regex strategies with the same ReDoS guard, sourceEmr narrowing) but selects a
    different rule subset (round9-revision3.md F2): a rule counts as "prefer" when
    action == 'prefer' (curated seed), OR when action == 'resolve' and the AI-learned
    documentClass == 'visit_summary' (the Stage-B extension of the jy4 resolve
    mechanism -- round9-revision3.md S3.1.2B). Unlike excludes, these clauses are OR'd
    together to RANK documents (preference_rank in the SELECT below); they never remove
    a row from the result set.

    Args:
        rules: List of document-type rule dicts (matchValue, matchStrategy,
               matchTarget, action, documentClass, sourceEmr).

    Returns:
        List of SQLAlchemy column expressions, one per applicable prefer/resolve rule.
    """
    clauses = []
    type_col = FhirResource.data["type"].astext

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        count_before = len(clauses)

        is_prefer = rule.get("action") == "prefer"
        is_learned_visit_summary = (
            rule.get("action") == "resolve" and rule.get("documentClass") == "visit_summary"
        )
        if not (is_prefer or is_learned_visit_summary):
            continue

        # D-09: skip loinc_code rules -- no LOINC field path established in FastAPI
        if rule.get("matchTarget") == "loinc_code":
            continue

        value = rule.get("matchValue", "")
        strategy = rule.get("matchStrategy", "ilike")

        if strategy == "ilike":
            clauses.append(type_col.ilike(f"%{value}%"))
        elif strategy == "exact":
            clauses.append(type_col == value)
        elif strategy == "regex":
            # CR-03: guard against ReDoS and invalid POSIX regex values (same as excludes).
            if not value or len(value) > 200:
                logger.warning(
                    "[_build_prefer_predicates] skipping regex rule -- "
                    "value absent or exceeds 200 chars"
                )
                continue
            try:
                re.compile(value)  # POSIX-compatible syntax pre-check
            except re.error as exc:
                logger.warning(
                    f"[_build_prefer_predicates] skipping invalid regex rule value: {exc}"
                )
                continue
            clauses.append(type_col.op("~")(value))
        if len(clauses) > count_before and rule.get("sourceEmr") not in (None, "", "all", "ALL", "*"):
            source = str(rule["sourceEmr"]).upper()
            clauses[-1] = and_(clauses[-1], cast(FhirResource.ehr_provider, String) == source)
        # unknown strategy: skip silently (defensive)

    return clauses


class FhirResourcesRepository:
    """Repository for querying FHIR resources from the database"""

    def __init__(self, session: AsyncSession):
        self.session = session
        # Visit-summary allowlist v2 state of the LAST get_document_references_with_attachments
        # call. Reset at the start of EVERY call (the service calls the repository up to three
        # times per attempt), never accumulated across calls.
        self.non_allowlisted_candidates_exist = False
        self.visit_summary_selection = None

    async def get_by_user(
        self, user_id: str, resource_types: list[str] | None = None, limit: int = 1000
    ) -> list[FhirResource]:
        """
        Fetch FHIR resources for a user, optionally filtered by resource types

        Args:
            user_id: The user's ID (Clerk ID)
            resource_types: Optional list of resource types to filter by
            limit: Maximum number of resources to return (default 1000)

        Returns:
            List of FhirResource objects
        """
        try:
            query = select(FhirResource).where(FhirResource.user_id == user_id)

            if resource_types:
                query = query.where(
                    cast(FhirResource.resource_type, String).in_(resource_types)
                )

            query = query.order_by(FhirResource.last_synced_at.desc()).limit(limit)

            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(
                f"Error fetching FHIR resources for user {user_id}", exc_info=e
            )
            raise e

    async def get_by_encounter(
        self, user_id: str, encounter_id: str, resource_types: list[str] | None = None
    ) -> list[FhirResource]:
        """
        Fetch FHIR resources linked to a specific encounter.
        Uses data->>'encounterReference' which contains values like "Encounter/98052727"

        This matches the NodeAPI implementation which queries:
        data->>'encounterReference' = 'Encounter/{encounter_id}'

        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID (ehr_resource_id from Encounter FHIR resource)
            resource_types: Optional list of resource types to filter by

        Returns:
            List of FhirResource objects linked to this encounter via encounterReference
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"

            # Query using data->>'encounterReference'
            # This will find all clinical resources (Observations, Conditions, etc.)
            # that reference this specific encounter
            query = select(FhirResource).where(
                FhirResource.user_id == user_id,
                func.jsonb_extract_path_text(FhirResource.data, "encounterReference")
                == encounter_reference,
            )

            if resource_types:
                query = query.where(
                    cast(FhirResource.resource_type, String).in_(resource_types)
                )

            query = query.order_by(FhirResource.last_synced_at.desc())

            result = await self.session.execute(query)
            resources = result.scalars().all()

            logger.info(
                f"Found {len(resources)} resources for encounter {encounter_reference} (user: {user_id[:8]}...)"
            )

            return resources
        except Exception as e:
            logger.error(
                f"Error fetching FHIR resources for encounter {encounter_id}",
                exc_info=e,
            )
            raise e

    async def get_resource_counts_by_encounter(
        self, user_id: str, encounter_id: str
    ) -> dict[str, int]:
        """
        Get count of each resource type linked to a specific encounter.
        Uses data->>'encounterReference' to find linked resources.

        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID

        Returns:
            Dictionary mapping resource_type to count
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"

            query = (
                select(
                    FhirResource.resource_type,
                    func.count(FhirResource.id).label("count"),
                )
                .where(
                    FhirResource.user_id == user_id,
                    func.jsonb_extract_path_text(
                        FhirResource.data, "encounterReference"
                    )
                    == encounter_reference,
                )
                .group_by(FhirResource.resource_type)
            )

            result = await self.session.execute(query)
            rows = result.all()

            return {row.resource_type: row.count for row in rows}
        except Exception as e:
            logger.error(
                f"Error getting resource counts for encounter {encounter_id}",
                exc_info=e,
            )
            raise e

    async def get_resource_counts(self, user_id: str) -> dict[str, int]:
        """
        Get count of each resource type for a user

        Args:
            user_id: The user's ID (Clerk ID)

        Returns:
            Dictionary mapping resource_type to count
        """
        try:
            query = (
                select(
                    FhirResource.resource_type,
                    func.count(FhirResource.id).label("count"),
                )
                .where(FhirResource.user_id == user_id)
                .group_by(FhirResource.resource_type)
            )

            result = await self.session.execute(query)
            rows = result.all()

            # Convert to dict, extracting string value (no longer enum)
            return {row.resource_type: row.count for row in rows}
        except Exception as e:
            logger.error(
                f"Error getting resource counts for user {user_id}", exc_info=e
            )
            raise e

    async def get_encounter_with_clinical_data(
        self, user_id: str, encounter_id: str, resource_types: list[str] | None = None
    ) -> list[FhirResource]:
        """
        Fetch encounter resource AND all clinical resources linked to it.
        This matches NodeAPI's getEncounterWithClinicalData behavior.

        Returns the Encounter resource itself PLUS all resources that reference it
        via data->>'encounterReference'.

        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID (ehr_resource_id from Encounter FHIR resource)
            resource_types: Optional list of resource types to filter by

        Returns:
            List containing:
            - The Encounter resource itself (where ehr_resource_id = encounter_id)
            - All clinical resources that reference this encounter (via encounterReference)
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"

            # Build query with two conditions:
            # 1. The Encounter resource itself (resource_type = 'Encounter' AND ehr_resource_id = encounter_id)
            # 2. Resources that reference this encounter (data->>'encounterReference' = 'Encounter/{id}')
            # Note: Cast resource_type to String to handle PostgreSQL enum type
            query = select(FhirResource).where(
                FhirResource.user_id == user_id,
                or_(
                    # The encounter resource itself
                    (
                        (cast(FhirResource.resource_type, String) == "Encounter")
                        & (FhirResource.ehr_resource_id == normalized_id)
                    ),
                    # Resources that reference this encounter
                    func.jsonb_extract_path_text(
                        FhirResource.data, "encounterReference"
                    )
                    == encounter_reference,
                ),
            )

            if resource_types:
                query = query.where(
                    cast(FhirResource.resource_type, String).in_(resource_types)
                )

            query = query.order_by(FhirResource.last_synced_at.desc())

            result = await self.session.execute(query)
            resources = result.scalars().all()

            logger.info(
                f"Found {len(resources)} resources (including encounter) for encounter {encounter_reference} (user: {user_id[:8]}...)"
            )

            return resources
        except Exception as e:
            logger.error(
                f"Error fetching encounter with clinical data for {encounter_id}",
                exc_info=e,
            )
            raise e

    async def get_by_id(self, resource_id: UUID) -> FhirResource | None:
        """
        Fetch a single FHIR resource by ID

        Args:
            resource_id: The FHIR resource UUID

        Returns:
            FhirResource object or None if not found
        """
        try:
            result = await self.session.execute(
                select(FhirResource).where(FhirResource.id == resource_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching FHIR resource {resource_id}", exc_info=e)
            raise e

    async def get_document_references_with_attachments(
        self,
        user_id: str,
        encounter_id: str,
        *,
        selection_profile: str = "legacy",
        rule_snapshot: tuple | None = None,
    ) -> list[FhirResource]:
        """
        Fetch DocumentReference resources that have attachments for a specific encounter.

        Two queries run (round9-revision3.md Fix 5, S3.3 steps 1/3): an INVENTORY query,
        UNCHANGED in shape from the pre-redesign version, that drives `document_inventory`
        telemetry over the full pre-exclusion row set -- its shape is a hard requirement,
        not an implementation detail, because it is compared for EQUALITY downstream by
        the SOURCE_MANIFEST_CHANGED guard (attachment_summarization.py); and a SELECTION
        query that is the actual document feed, with exclude rules AND the
        missing-attachments predicate pushed into WHERE as real filter terms (not just a
        SELECT label), so the LIMIT below operates on real candidates instead of being
        starved by rows that get discarded after the fact -- this is the actual fix for
        RESOURCE_LIMIT_EXCEEDED (a raw LIMIT upstream of exclude filtering previously
        starved the cap of real candidates on heavily-excluded encounters).

        Filters (SELECTION query only -- the INVENTORY query keeps the pre-redesign
        user_id/resource_type/encounterReference-only WHERE):
        - resource_type = 'DocumentReference'
        - encounterReference matches the encounter_id
        - data->'attachments' exists and is a non-empty JSON array (type-guarded:
          jsonb_array_length() raises on non-array jsonb, so this is NOT the naive
          one-line jsonb_array_length(...) > 0 -- see the CASE below)
        - document type is not excluded by active document-type rules (PIPE-05)

        Visit-summary allowlist v2 (flag-gated): when settings.VISIT_SUMMARY_ALLOWLIST_ENABLED and
        selection_profile == 'visit_summary_preferred', the SELECTION WHERE additionally requires
        (label include OR LOINC code) AND NOT deny (``_build_allowlist_predicates``), BEFORE the
        LIMIT. The INVENTORY query is unchanged. Per-call attributes (reset at the start of every
        call): ``non_allowlisted_candidates_exist`` (set only when the selection came back empty and
        an EXISTS probe finds candidates the allowlist rejected) and ``visit_summary_selection``
        (capped telemetry; None when the allowlist is off).

        Ordering (SELECTION query):
        - selection_profile='legacy' (default; procedure/comprehensive callers):
          document date descending, unchanged from the pre-redesign behavior.
        - selection_profile='visit_summary_preferred' (attachment_summarization only):
          preference_rank ASC, include_for_summary_rank ASC, document date DESC,
          ehr_resource_id ASC (final tiebreak -- makes the order total/deterministic,
          which the cap below requires: a non-total order would make the cap itself
          non-deterministic across identical re-fetches and destabilize the manifest).
          preference_rank is 0 for documents matching a curated 'prefer' rule or a
          learned 'resolve' rule with documentClass='visit_summary' (_build_prefer_
          predicates), else 1. include_for_summary_rank is 0 when the AI classifier
          flagged includeForSummary=true, else 1 -- this SUBSUMES the soft preference
          that used to live as a second, Python-side narrowing step in
          attachment_summarization.py (round9-revision3.md S3.1.2A). Because it is the
          ORDER BY's second key within each preference_rank band, a plain LIMIT over
          this order is already cap-filling (flagged documents fill the cap before
          unflagged ones, within each band) -- no extra code is required for that
          property, it is emergent from ORDER BY + LIMIT.

        Cap: LIMIT is DOCUMENT_SELECTION_CAP + 1, not DOCUMENT_SELECTION_CAP -- the +1
        is a truncation DETECTOR, not slack (round9-revision3.md F7c). document_ingestion.
        MAX_DOCUMENTS (attachment-counted, not DocumentReference-counted -- a format-dedup
        pass sits between the two units) is the real binding cap; this repository's LIMIT
        only has to supply enough rows that ingestion's own cap can actually trip when
        truncation is real, instead of silently running out of DocumentReferences first
        and never noticing (which would make the existing partial/truncation-disclosure
        machinery never fire even though real truncation occurred). The pre-redesign
        `len(inventory) > 100` raise is REMOVED here (S3.3 step 5) for every caller and
        every selection_profile -- not just the preferred one.

        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID
            selection_profile: 'legacy' (default) or 'visit_summary_preferred'.
            rule_snapshot: optional pre-resolved (rules, provenance) tuple, exactly as
                returned by DocumentTypeRulesClient.resolve_rules(). When provided, rule
                resolution is skipped here. Callers that fetch twice per summarization
                attempt (the manifest re-check in attachment_summarization.py) MUST
                resolve once and pass the SAME snapshot to both calls, or a rule-tier
                flip between calls changes the ordered set, changes the manifest hash,
                and raises a retryable SOURCE_MANIFEST_CHANGED (round9-revision3.md
                S3.3 step 4 / risk R7b). Callers that fetch once (procedure,
                comprehensive) can omit this and resolve fresh as before.

        Returns:
            List of FhirResource objects (DocumentReferences) with attachments, ordered
            per selection_profile above.
        """
        # Reset the per-call allowlist state FIRST (the service calls this up to three times per
        # attempt: initial fetch + two manifest re-checks); a stale discriminator or telemetry
        # from an earlier call must never leak into this one.
        self.non_allowlisted_candidates_exist = False
        self.visit_summary_selection = None
        allow_on = bool(
            selection_profile == "visit_summary_preferred"
            and get_settings().VISIT_SUMMARY_ALLOWLIST_ENABLED
        )

        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"

            # Fetch active rules from DocumentTypeRulesClient (PIPE-05), or use the
            # caller's pre-resolved snapshot (S3.3 step 4 / R7b).
            # Uses three-tier fallback: live → stale → HARDCODED_DOCREF_EXCLUDES floor.
            # D-04: if exclude_clauses is empty, ~or_() is not applied (qualify-all).
            if rule_snapshot is not None:
                rules, provenance = rule_snapshot
            else:
                rules_client = get_document_type_rules_client()
                rules, provenance = await rules_client.resolve_rules()
            self.eligibility_provenance = provenance
            exclude_clauses = _build_exclude_predicates(rules)
            prefer_clauses = _build_prefer_predicates(rules)

            base_predicates = (
                FhirResource.user_id == user_id,
                cast(FhirResource.resource_type, String) == "DocumentReference",
                func.jsonb_extract_path_text(FhirResource.data, "encounterReference")
                == encounter_reference,
            )

            # --- INVENTORY query: UNCHANGED from the pre-redesign shape (S3.3 step 3,
            # hard requirement). Drives document_inventory telemetry over the FULL
            # pre-exclusion row set. Do not add the attachments predicate or push
            # excludes into WHERE here -- either would change total_references/
            # excluded_documents/manifest and raise a retryable SOURCE_MANIFEST_CHANGED
            # on the first cache-hit path after deploy (risk R7c).
            from sqlalchemy import case as sql_case, literal
            exclusion_decision = (
                sql_case(
                    *[
                        (func.coalesce(clause, False), literal(f"document_type_rule:{index}"))
                        for index, clause in enumerate(exclude_clauses)
                    ],
                    else_=None,
                )
                if exclude_clauses
                else literal(None)
            )
            inventory_query = (
                select(FhirResource, exclusion_decision.label("exclusion_reason"))
                .where(and_(*base_predicates))
                .order_by(func.jsonb_extract_path_text(FhirResource.data, "date").desc())
                .limit(101)
            )
            inventory_result = await self.session.execute(
                inventory_query.execution_options(populate_existing=True)
            )
            inventory = inventory_result.all()
            # The pre-redesign raise ("if len(inventory) > 100: raise DOCUMENT_LIMIT_EXCEEDED")
            # is REMOVED here (S3.3 step 5) -- order-then-cap on the SELECTION query below
            # replaces it, for every caller and every selection_profile.
            excluded = [
                {"source_id": str(resource.ehr_resource_id), "reason": reason}
                for resource, reason in inventory
                if reason is not None
            ]
            from src.app.services.summary_outcomes import source_manifest
            self.document_inventory = {
                "total_references": len(inventory),
                "excluded_documents": len(excluded),
                "exclusions": excluded[:20],
                "exclusions_omitted": max(0, len(excluded) - 20),
                "manifest": source_manifest([resource for resource, _ in inventory]),
            }
            if allow_on:
                # Telemetry is computed in Python over the (unchanged) INVENTORY rows with the
                # same matcher the SQL twin is parity-tested against. It is deliberately NOT
                # added to document_inventory (that object is copied into the synthesis prompt
                # context; r7-n-01): it lives in its own attribute and the service merges it
                # into summary_metadata.visit_summary_selection.
                self.visit_summary_selection = _allowlist_telemetry(inventory)

            # --- SELECTION query: the actual document feed (S3.3 steps 1-2, 5, 6).
            # Excludes and the missing-attachments predicate are real WHERE terms here
            # (not SELECT labels), so LIMIT operates on candidates that will actually be
            # used.
            attachments_ok = sql_case(
                (
                    func.jsonb_typeof(FhirResource.data["attachments"]) == "array",
                    func.jsonb_array_length(FhirResource.data["attachments"]) > 0,
                ),
                else_=False,
            )
            selection_where = list(base_predicates) + [attachments_ok]
            if exclude_clauses:
                # NULL-safe NOT: a document whose type is NULL makes every ILIKE/regex
                # rule evaluate to NULL, and `NOT (NULL)` is NULL -> the row would be
                # silently dropped. The INVENTORY query above already coalesces each
                # clause to False, so selection must treat "unknown" as "not excluded"
                # too (allowlist v2 prerequisite (b); applies to every selection profile).
                selection_where.append(~func.coalesce(or_(*exclude_clauses), False))

            # Everything a document needs EXCEPT the allowlist (used by the empty-selection
            # discriminator below).
            pre_allowlist_where = list(selection_where)
            if allow_on:
                include_term, loinc_term, deny_term = _build_allowlist_predicates()
                # allow term BEFORE the LIMIT: (label include OR LOINC code) AND NOT deny. All
                # three terms are coalesced to false, so this is plain two-valued logic.
                selection_where.append(or_(include_term, loinc_term))
                selection_where.append(~deny_term)

            selection_query = select(FhirResource).where(and_(*selection_where))

            if selection_profile == "visit_summary_preferred":
                preference_rank = (
                    sql_case((or_(*prefer_clauses), literal(0)), else_=literal(1))
                    if prefer_clauses
                    else literal(1)
                )
                include_for_summary_rank = sql_case(
                    (
                        func.jsonb_extract_path_text(FhirResource.data, "includeForSummary")
                        == "true",
                        literal(0),
                    ),
                    else_=literal(1),
                )
                selection_query = selection_query.order_by(
                    preference_rank.asc(),
                    include_for_summary_rank.asc(),
                    func.jsonb_extract_path_text(FhirResource.data, "date").desc(),
                    FhirResource.ehr_resource_id.asc(),
                )
            else:
                selection_query = selection_query.order_by(
                    func.jsonb_extract_path_text(FhirResource.data, "date").desc()
                )

            # DOCUMENT_SELECTION_CAP + 1, not just the cap -- see docstring ("truncation
            # DETECTOR, not slack"). document_ingestion.MAX_DOCUMENTS owns the binding cap.
            selection_result = await self.session.execute(
                selection_query.limit(DOCUMENT_SELECTION_CAP + 1).execution_options(
                    populate_existing=True
                )
            )
            resources = selection_result.scalars().all()

            if allow_on and not resources:
                # Empty-selection discriminator: is the selection empty because every candidate
                # (attachments present, not DB-excluded) was rejected by the allowlist -- vs
                # simply having no candidates at all (the existing no_documents state)?
                candidate_query = (
                    select(literal(1)).select_from(FhirResource).where(and_(*pre_allowlist_where)).limit(1)
                )
                candidate_result = await self.session.execute(candidate_query)
                self.non_allowlisted_candidates_exist = candidate_result.first() is not None

            logger.info(
                f"Found {len(resources)} DocumentReferences with attachments for "
                f"encounter {encounter_reference} (user: {user_id[:8]}...)"
            )

            return resources

        except Exception as e:
            logger.error(
                f"Error fetching DocumentReferences with attachments for "
                f"encounter {encounter_id}",
                exc_info=e,
            )
            raise e
