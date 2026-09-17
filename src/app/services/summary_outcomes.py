"""Deterministic user messages carried by existing summary JSON and metadata."""
MESSAGES = {
    "unsupported": "We couldn’t summarize these documents because their format or embedded content isn’t supported. Please provide a supported document format.",
    "unavailable": "We couldn’t create a summary because the documents couldn’t be processed. Please try again later.",
    "service_unavailable": "We couldn’t create a summary right now because the summarization service is unavailable. Please try again later.",
    "partial": "Some documents couldn’t be processed. Important information may be missing.",
    "no_documents": "No clinical documents are available to summarize for this appointment.",
}
SERVICE_UNAVAILABLE_CODES = frozenset({
    "MODEL_UNAVAILABLE", "MODEL_TIMEOUT", "MODEL_RATE_LIMITED", "MODEL_AUTH_FAILED", "OCR_TIMEOUT",
})
PIPELINE_VERSION = "document-safety-4"


def nonclinical_payload(request, source, *, state="unavailable", errors=()):
    """Existing summary contract with no stale or fabricated clinical fields."""
    errors = list(errors)
    message = unavailable_message(errors) if state == "unavailable" else MESSAGES[state]
    return {"summary_text": message, "user_id": request.user_id,
            "created_by": request.user_id, "updated_by": request.user_id,
            "key_points": [], "medications": [], "diagnoses": [],
            "instructions": [], "recommendations": [], "data": {},
            "summary_metadata": {"source": source, **outcome_metadata(state, errors)}}


def outcome_metadata(state, errors=()):
    from src.app.services.processing_metrics import record
    record("coverage", state)
    from datetime import datetime, timezone
    from src.app.services.summary_runtime import _current_budget
    budget = _current_budget.get()
    from src.app.services.processing_errors import describe_error
    error_items = [item for item in errors if isinstance(item, dict)]
    normalized_errors = [describe_error(item.get("error"), item.get("source_id")) for item in error_items[:20]]
    started_at = budget.started_at if budget else datetime.now(timezone.utc).isoformat()
    return {"attempt_started_at": started_at, "processing_outcome": state, "pipeline_version": PIPELINE_VERSION,
            "processing_errors": normalized_errors, "processing_error_count": len(error_items), "processing_errors_omitted": max(0, len(error_items) - len(normalized_errors)), "validation_status": "passed" if state in {"complete", "partial"} else "not_applicable", "is_clinical_summary": state in {"complete", "partial"}}


def source_manifest(references):
    import hashlib
    import json
    entries = [{"id": str(item.ehr_resource_id), "data": item.data, "updated_at": str(getattr(item, "updated_at", ""))} for item in references]
    entries.sort(key=lambda item: item["id"])
    return hashlib.sha256(json.dumps(entries, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def unavailable_message(errors):
    codes = {item.get("error") for item in errors if isinstance(item, dict)}
    if codes & SERVICE_UNAVAILABLE_CODES:
        return MESSAGES["service_unavailable"]
    return MESSAGES["unsupported"] if codes == {"UNSUPPORTED_FORMAT"} else MESSAGES["unavailable"]
