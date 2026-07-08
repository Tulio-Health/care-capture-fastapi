"""Pydantic models for batch-shaped FHIR DocumentReference type inference.

A single item is just a batch of 1 — there is no separate single-item
request/response model or route (RESEARCH.md §7a).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentTypeInferenceRequest(BaseModel):
    """Minimal CodeableConcept-derived fields only. Never includes raw document/attachment content."""

    id: str = Field(
        ...,
        description=(
            "Pure correlation handle for this batch item (e.g. the source DocumentReference's "
            "resourceId or a stable local index) — never treated as content. Excluded from the "
            "Redis cache-key hash so content-identical items with different ids share one cache entry."
        ),
    )
    type_code: Optional[str] = Field(None, description="$.type.coding[0].code — LOINC code or NullFlavor 'UNK'")
    type_system: Optional[str] = Field(None, description="$.type.coding[0].system")
    category_text: Optional[str] = Field(None, description="$.category[*].text, joined if multiple")
    category_codes: List[str] = Field(default_factory=list, description="$.category[*].coding[*].code")
    content_title: Optional[str] = Field(None, description="$.content[0].attachment.title")
    content_type: Optional[str] = Field(None, description="$.content[0].attachment.contentType (MIME)")
    raw_display: Optional[str] = Field(
        None, description="$.type.coding[0].display as-is, even when unhelpful, e.g. 'unknown'"
    )


class DocumentTypeInferenceResponse(BaseModel):
    """Structured classification for a single DocumentReference, correlated back via `id`."""

    id: str = Field(
        ...,
        description=(
            "Echoes the corresponding request item's id, so the caller can correlate each "
            "response to its request. On a cache hit, this is overwritten with the CURRENT "
            "requester's id before being returned (the id baked into a stored cache entry "
            "belongs to whichever request first wrote it)."
        ),
    )
    normalized_type: str = Field(
        ..., description="Short human-readable label, free text — written straight into DocumentReference.type"
    )
    include_for_summary: bool = Field(
        ..., description="True only for clinically substantive documents; False for administrative/non-clinical ones"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model self-reported confidence in normalized_type")


class DocumentTypeInferenceBatchRequest(BaseModel):
    """Batch wrapper — a single item is just a batch of 1; no separate single-item model/route exists."""

    items: List[DocumentTypeInferenceRequest] = Field(
        ..., description="One or more document metadata items to classify."
    )


class DocumentTypeInferenceBatchResponse(BaseModel):
    """Batch wrapper — one classification per successfully-processed input item."""

    items: List[DocumentTypeInferenceResponse] = Field(
        ...,
        description=(
            "One classification per input item that was successfully resolved (cache hit or "
            "fresh inference). Order is not guaranteed to match request order — correlate via id. "
            "An item may be absent if the model dropped/conflated its id during a batch LLM call."
        ),
    )
