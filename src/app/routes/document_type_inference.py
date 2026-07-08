"""Batch-shaped document-type-inference route.

Per-item Redis cache is checked first (cache key excludes the correlation `id`); only
cache-miss items are grouped into a single LLM call via `DocumentTypeInferenceChain.infer_batch`.
This route is NOT added to `ClerkAuthMiddleware`'s `EXCLUDED_PATHS`/`EXCLUDED_PATH_PREFIXES`, so
it is automatically protected by the existing global middleware (valid `x-clerk-jwt` OR a
matching `x-internal-service-key` — the same contract emr-connector's client uses).
"""

import hashlib
import json
import logging
from typing import Dict, List

from fastapi import APIRouter

from src.app.cache.redis import redis_client
from src.app.chains.document_type_inference.chain import DocumentTypeInferenceChain
from src.app.models.document_type_inference import (
    DocumentTypeInferenceBatchRequest,
    DocumentTypeInferenceBatchResponse,
    DocumentTypeInferenceRequest,
    DocumentTypeInferenceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/care-capture", tags=["document-type-inference"])

_CACHE_KEY_VERSION = "v1"
_CACHE_TTL_SECONDS = 2_592_000  # 30 days
_CACHE_CONFIDENCE_THRESHOLD = 0.7

# Instantiated once at MODULE scope (not per-request) so the lazy model/agent properties
# are populated once and reused across requests — a deliberate choice for this new,
# potentially-hot, cost-sensitive endpoint (unlike translation.py's TranslationChain,
# which is instantiated per-request; only the lazy-property design is mirrored, not that
# specific per-request-instantiation detail).
chain = DocumentTypeInferenceChain()


def _cache_key(item: DocumentTypeInferenceRequest) -> str:
    """
    Compute the Redis cache key for a single inference request item.

    The `id` field is EXCLUDED from the hash input — it is a pure correlation handle, never
    content. Two content-identical items with different `id`s MUST share one cache entry, or
    30-day caching silently degrades for the common case of the same document-type pattern
    recurring across different patients/resourceIds under different `id`s.
    """
    payload = item.model_dump(exclude={"id"})
    canonical = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"doctype-infer:{_CACHE_KEY_VERSION}:{digest}"


@router.post(
    "/document-type-inference",
    response_model=DocumentTypeInferenceBatchResponse,
    summary="Batch Document Type Inference",
    description=(
        "Infer a normalized document type and summary-eligibility signal for a batch of FHIR "
        "DocumentReference metadata items. Each item is checked against a 30-day Redis cache "
        "before any uncached items are grouped into a single LLM call. A single item is just "
        "a batch of 1 — there is no separate single-item route."
    ),
)
async def infer_document_types(
    batch: DocumentTypeInferenceBatchRequest,
) -> DocumentTypeInferenceBatchResponse:
    cache_hits: Dict[str, DocumentTypeInferenceResponse] = {}
    cache_misses: List[DocumentTypeInferenceRequest] = []

    for item in batch.items:
        key = _cache_key(item)
        try:
            cached_raw = redis_client.get(key)
        except Exception as e:
            logger.warning(f"Redis get failed for doctype-infer cache key, treating as cache miss: {e}")
            cached_raw = None
        if not cached_raw:
            cache_misses.append(item)
            continue
        try:
            cached_response = DocumentTypeInferenceResponse.model_validate_json(cached_raw)
        except Exception as e:
            logger.warning(f"Failed to deserialize cached document-type-inference entry: {e}")
            cache_misses.append(item)
            continue
        # A cache hit necessarily came from a DIFFERENT original request (id is excluded from
        # the hash) — the id baked into the stored entry belongs to whichever request first
        # wrote it, not the current requester. Overwrite before returning, or the emr-connector
        # side's id-based remerge would silently misattribute this result.
        cached_response.id = item.id
        cache_hits[item.id] = cached_response

    inferred_by_id: Dict[str, DocumentTypeInferenceResponse] = {}
    if cache_misses:
        misses_by_id = {item.id: item for item in cache_misses}
        inferred = await chain.infer_batch(cache_misses)
        for response in inferred:
            originating_item = misses_by_id.get(response.id)
            if originating_item is None:
                # The model returned an id we never asked about for this chunk — nothing to
                # correlate it to or cache it against; drop it rather than risk misattribution.
                logger.warning(f"infer_batch returned unrecognized id {response.id!r}, discarding")
                continue
            inferred_by_id[response.id] = response
            if response.confidence >= _CACHE_CONFIDENCE_THRESHOLD:
                try:
                    redis_client.set(
                        _cache_key(originating_item),
                        response.model_dump_json(),
                        expiry=_CACHE_TTL_SECONDS,
                    )
                except Exception as e:
                    logger.warning(f"Redis set failed for doctype-infer cache key, continuing without caching: {e}")

    # Order-preserving, id-keyed remerge — independent of whatever order the LLM itself
    # returned items in (RESEARCH.md §7a's reorder-risk framing).
    merged: List[DocumentTypeInferenceResponse] = []
    for item in batch.items:
        if item.id in cache_hits:
            merged.append(cache_hits[item.id])
        elif item.id in inferred_by_id:
            merged.append(inferred_by_id[item.id])
        # else: infer_batch dropped/conflated this id (whole-chunk failure or model output
        # shorter than requested) — degrade gracefully, simply omit it from the response.

    return DocumentTypeInferenceBatchResponse(items=merged)
