"""T6 / T8 / T9 / T11 / T12 + r7-n-01 -- the `no_visit_summary_documents` outcome and the
`visit_summary_selection` telemetry placement (allowlist v2).

* T6   service: candidates exist but none is a visit summary -> dedicated non-clinical row, ZERO LLM
       work, keeps async_token + eligibility snapshot, adds regeneration_forced.
* T8   the frozen user-facing copy (typographic apostrophe, owner decision O7).
* T9   consumers treat the row as non-clinical (comprehensive: no FHIR fallback; cache: miss;
       metrics stage registered).
* T11  telemetry caps survive into the row.
* T12  sync-route contract: `summaryMetadata.processing_outcome`, no top-level `metadata`.
* r7-n-01  telemetry is in a SIBLING `visit_summary_selection` block merged into summary_metadata;
       it is NEVER in `appointment_context` / `document_inventory` (those reach the synthesis
       prompt), and `allowlist_version` reaches the cache fingerprint through `selection_policy`.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.app.models.attachment_summarization import AttachmentSummarizationRequest, DocumentAttachment
from src.app.models.conversation_summaries import ConversationSummary
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
    _static_fallback_summary_data,
)
from src.app.services.summary_outcomes import MESSAGES, NO_VISIT_SUMMARY_DOCUMENTS, outcome_metadata

EXPECTED_MESSAGE = "No visit summary or visit note is available for this appointment, so a summary wasn\u2019t created."
TELEMETRY_KEYS = ("visit_summary_selection", "not_allowlisted_documents", "not_allowlisted_types", "allowlist_version")


def _request(**kw):
    return AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), async_token="tok-1", **kw)


def _appointment():
    return SimpleNamespace(
        appointment_date=datetime(2026, 1, 1), purpose="Follow-up", ehr_entity_id="enc-123", provider_id=None
    )


class _Summaries:
    def __init__(self):
        self.upsert_calls = []

    async def upsert(self, appointment_id, summary_data):
        self.upsert_calls.append((appointment_id, summary_data))
        now = datetime.now(timezone.utc)
        return SimpleNamespace(id=uuid4(), appointment_id=appointment_id, created_at=now, updated_at=now, **summary_data)

    async def get_by_appointment_id_and_source(self, *a, **k):
        return None


TELE = {
    "allowlist_version": "visit-summary-allowlist-v2",
    "not_allowlisted_documents": 3,
    "not_allowlisted_types": {"diagnostic imaging study": 2, "patient instructions": 1},
}


def _service(*, selection=TELE, candidates=True):
    service = AttachmentSummarizationService.__new__(AttachmentSummarizationService)
    logs = []
    service.logger = SimpleNamespace(
        info=lambda m, *a, **k: logs.append(m), debug=lambda *a, **k: None, warning=lambda *a, **k: None
    )
    service.logs = logs
    service.summaries_repo = _Summaries()
    service.fhir_repo = SimpleNamespace(
        eligibility_provenance={"tier": "live", "digest": "d"},
        document_inventory={"total_references": 3, "excluded_documents": 0, "exclusions": [], "exclusions_omitted": 0, "manifest": "m"},
        visit_summary_selection=selection,
        non_allowlisted_candidates_exist=candidates,
    )
    service.llm_work = []

    async def no_work(*a, **k):
        service.llm_work.append("called")
        raise AssertionError("no extraction / LLM work may happen for this outcome")

    service._process_attachments = no_work
    service._run_ai_analysis = no_work
    return service


def _wire(monkeypatch, service, doc_references):
    async def appt(req):
        return _appointment(), "Dr. Smith"

    async def fetch(req, appointment):
        return doc_references

    monkeypatch.setattr(service, "_fetch_appointment_details", appt)
    monkeypatch.setattr(service, "_fetch_document_references", fetch)
    monkeypatch.setattr(
        "src.app.services.summarization.attachment_summarization.get_document_type_rules_client",
        lambda: SimpleNamespace(resolve_rules=AsyncMock(return_value=([], {}))),
    )


# ---------------------------------------------------------------------------------------------
# T8: the frozen copy + registration
# ---------------------------------------------------------------------------------------------
def test_t8_message_is_exactly_the_owner_approved_copy():
    assert MESSAGES[NO_VISIT_SUMMARY_DOCUMENTS] == EXPECTED_MESSAGE
    assert "\u2019" in EXPECTED_MESSAGE and "'" not in EXPECTED_MESSAGE
    assert NO_VISIT_SUMMARY_DOCUMENTS == "no_visit_summary_documents"


def test_outcome_metadata_is_non_clinical_and_counted():
    from src.app.services import processing_metrics

    before = processing_metrics.snapshot().get("coverage:no_visit_summary_documents", 0)
    meta = outcome_metadata(NO_VISIT_SUMMARY_DOCUMENTS)
    assert meta["processing_outcome"] == "no_visit_summary_documents"
    assert meta["is_clinical_summary"] is False and meta["validation_status"] == "not_applicable"
    assert meta["processing_errors"] == [] and meta["processing_error_count"] == 0
    assert processing_metrics.snapshot()["coverage:no_visit_summary_documents"] == before + 1


def test_static_payload_default_is_unchanged_no_documents():
    payload = _static_fallback_summary_data(_request(), _appointment(), "Dr. X")
    assert payload["summary_text"] == MESSAGES["no_documents"]
    assert payload["summary_metadata"]["processing_outcome"] == "no_documents"


# ---------------------------------------------------------------------------------------------
# T6
# ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_t6_new_outcome_row_no_llm_keeps_token_and_snapshot(monkeypatch):
    service = _service()
    request = _request()
    _wire(monkeypatch, service, [])

    result = await service.analyze_attachments(request)

    assert result is not None and service.llm_work == []
    assert len(service.summaries_repo.upsert_calls) == 1
    appointment_id, data = service.summaries_repo.upsert_calls[0]
    assert appointment_id == request.appointment_id
    assert data["summary_text"] == EXPECTED_MESSAGE
    assert (data["key_points"], data["medications"], data["diagnoses"], data["instructions"], data["recommendations"], data["data"]) == ([], [], [], [], [], {})
    meta = data["summary_metadata"]
    assert meta["processing_outcome"] == "no_visit_summary_documents"
    assert meta["is_clinical_summary"] is False and meta["validation_status"] == "not_applicable"
    assert meta["source"] == "attachment_summary"
    assert meta["async_token"] == "tok-1"
    assert meta["document_rule_provenance"] == {"tier": "live", "digest": "d"}
    assert meta["document_inventory"]["total_references"] == 3
    assert meta["regeneration_forced"] is False
    assert meta["total_documents"] == 0 and meta["successful_documents"] == 0
    assert meta["visit_summary_selection"] == TELE
    # telemetry lives ONLY in the sibling block
    assert "not_allowlisted_types" not in meta and "not_allowlisted_types" not in meta["document_inventory"]


@pytest.mark.asyncio
async def test_t6_regeneration_forced_follows_force_regenerate(monkeypatch):
    service = _service()
    _wire(monkeypatch, service, [])
    await service.analyze_attachments(_request(force_regenerate=True))
    assert service.summaries_repo.upsert_calls[0][1]["summary_metadata"]["regeneration_forced"] is True


@pytest.mark.asyncio
async def test_t6_no_candidates_at_all_stays_no_documents_even_with_the_allowlist_on(monkeypatch):
    service = _service(selection={**TELE, "not_allowlisted_documents": 0, "not_allowlisted_types": {}}, candidates=False)
    _wire(monkeypatch, service, [])
    await service.analyze_attachments(_request())
    _, data = service.summaries_repo.upsert_calls[0]
    assert data["summary_text"] == MESSAGES["no_documents"]
    assert data["summary_metadata"]["processing_outcome"] == "no_documents"
    assert "regeneration_forced" not in data["summary_metadata"]


@pytest.mark.asyncio
async def test_t6_flag_off_empty_selection_is_the_unchanged_no_documents_row(monkeypatch):
    service = _service(selection=None, candidates=False)
    _wire(monkeypatch, service, [])
    await service.analyze_attachments(_request())
    _, data = service.summaries_repo.upsert_calls[0]
    assert data["summary_text"] == MESSAGES["no_documents"]
    assert "visit_summary_selection" not in data["summary_metadata"]
    assert not any("visit_summary_allowlist_dropped" in m for m in service.logs)


@pytest.mark.asyncio
async def test_t6_flag_off_never_emits_the_new_outcome_even_if_a_stale_attribute_is_true(monkeypatch):
    service = _service(selection=None, candidates=True)  # repo attrs inconsistent: selection None => allowlist off
    _wire(monkeypatch, service, [])
    await service.analyze_attachments(_request())
    assert service.summaries_repo.upsert_calls[0][1]["summary_metadata"]["processing_outcome"] == "no_documents"


@pytest.mark.asyncio
async def test_dropped_log_line(monkeypatch):
    service = _service()
    request = _request()
    _wire(monkeypatch, service, [])
    await service.analyze_attachments(request)
    line = next(m for m in service.logs if m.startswith("visit_summary_allowlist_dropped"))
    assert f"appointment_id={request.appointment_id} version=v2 n=3 types=diagnostic imaging study|patient instructions" in line


# ---------------------------------------------------------------------------------------------
# T11 + r7-n-01
# ---------------------------------------------------------------------------------------------
def _doc(resource_id="doc-1"):
    return DocumentAttachment(
        file_path=f"s3://b/{resource_id}.txt", content_type="text/plain", resource_id=resource_id,
        extracted_text="Visit note text", content_sha256="a" * 64, parsed_text_sha256="b" * 64,
        parser_version="v", document_type="Progress Note", title="t",
    )


def _complete_payload(*a, **k):
    return {
        "summary_text": "ok", "user_id": uuid4(), "created_by": uuid4(), "updated_by": uuid4(),
        "key_points": [], "medications": [], "diagnoses": [], "instructions": [], "recommendations": [], "data": {},
        "summary_metadata": {"source": "attachment_summary", **outcome_metadata("complete"), "extraction_errors": []},
    }


@pytest.mark.asyncio
async def test_t11_telemetry_caps_reach_the_row_and_r7_nothing_reaches_the_prompt_context(monkeypatch):
    big = {f"label {i:02d}": 15 - i for i in range(10)}
    tele = {"allowlist_version": "visit-summary-allowlist-v2", "not_allowlisted_documents": 99, "not_allowlisted_types": big}
    service = _service(selection=tele, candidates=False)
    service._process_attachments = AsyncMock(return_value=[_doc()])
    seen = {}

    async def fake_ai(appointment_context, documents, *, encounter_id=None):
        seen["context"] = appointment_context
        return SimpleNamespace(documents_analyzed=1)

    service._run_ai_analysis = fake_ai
    refs = [SimpleNamespace(ehr_resource_id="doc-1", data={"type": "Progress Note"}, updated_at=None)]
    _wire(monkeypatch, service, refs)
    service._prepare_summary_data = _complete_payload
    monkeypatch.setattr("src.app.services.validated_summary.require_validated_summary", lambda r: None)
    service.s3_client = SimpleNamespace(validate_download_versions=AsyncMock())
    fingerprints = []

    def fake_fp(documents, manifest, context, settings, selection_policy=None):
        fingerprints.append((json.dumps(context, sort_keys=True, default=str), selection_policy))
        return "fp"

    monkeypatch.setattr("src.app.services.summary_cache.attachment_fingerprint", fake_fp)
    monkeypatch.setattr("src.app.services.summary_cache.verified_attachment_cache", AsyncMock(return_value=None))

    await service.analyze_attachments(_request())

    # (a) the model-visible context carries no telemetry key anywhere
    prompt_like = json.dumps({"appointment_context": seen["context"], "validated_source_records": []}, default=str)
    for key in TELEMETRY_KEYS:
        assert key not in prompt_like, key
    assert "label 00" not in prompt_like and "document_eligibility" in prompt_like  # eligibility itself is unchanged
    # (b) the fingerprint context is the same model-visible context; the policy rides separately
    assert fingerprints[0][1] == {"allowlist_version": "visit-summary-allowlist-v2"}
    for key in TELEMETRY_KEYS:
        assert key not in fingerprints[0][0]
    # (c) the row carries the sibling block, capped
    _, data = service.summaries_repo.upsert_calls[0]
    block = data["summary_metadata"]["visit_summary_selection"]
    assert block == tele and len(block["not_allowlisted_types"]) <= 10
    assert all(len(label) <= 64 for label in block["not_allowlisted_types"])
    assert "not_allowlisted_types" not in data["summary_metadata"]["document_inventory"]
    assert data["summary_metadata"]["source_fingerprint"] == "fp"


@pytest.mark.asyncio
async def test_flag_off_passes_no_selection_policy_and_adds_no_block(monkeypatch):
    service = _service(selection=None, candidates=False)
    service._process_attachments = AsyncMock(return_value=[_doc()])
    service._run_ai_analysis = AsyncMock(return_value=SimpleNamespace(documents_analyzed=1))
    refs = [SimpleNamespace(ehr_resource_id="doc-1", data={"type": "Progress Note"}, updated_at=None)]
    _wire(monkeypatch, service, refs)
    service._prepare_summary_data = _complete_payload
    monkeypatch.setattr("src.app.services.validated_summary.require_validated_summary", lambda r: None)
    service.s3_client = SimpleNamespace(validate_download_versions=AsyncMock())
    policies = []
    monkeypatch.setattr(
        "src.app.services.summary_cache.attachment_fingerprint",
        lambda documents, manifest, context, settings, selection_policy=None: policies.append(selection_policy) or "fp",
    )
    monkeypatch.setattr("src.app.services.summary_cache.verified_attachment_cache", AsyncMock(return_value=None))
    await service.analyze_attachments(_request())
    assert policies == [None]
    assert "visit_summary_selection" not in service.summaries_repo.upsert_calls[0][1]["summary_metadata"]


def test_selection_policy_changes_the_fingerprint_only_when_passed(monkeypatch):
    from src.app.services import summary_cache

    doc = _doc()
    settings = SimpleNamespace(DOCUMENT_VERIFICATION_MODEL="m", DOCUMENT_OCR_MODEL="o", ENABLE_DOCUMENT_OCR=False)
    monkeypatch.setattr(summary_cache, "require_parsed", lambda d: None)
    base = summary_cache.attachment_fingerprint([doc], "manifest", {"c": 1}, settings)
    assert base == summary_cache.attachment_fingerprint([doc], "manifest", {"c": 1}, settings, selection_policy=None)
    v2 = summary_cache.attachment_fingerprint([doc], "manifest", {"c": 1}, settings, selection_policy={"allowlist_version": "visit-summary-allowlist-v2"})
    v3 = summary_cache.attachment_fingerprint([doc], "manifest", {"c": 1}, settings, selection_policy={"allowlist_version": "visit-summary-allowlist-v3"})
    assert len({base, v2, v3}) == 3


# ---------------------------------------------------------------------------------------------
# T9: consumers
# ---------------------------------------------------------------------------------------------
def _new_row_summary():
    payload = _static_fallback_summary_data(_request(), _appointment(), "Dr. X", state=NO_VISIT_SUMMARY_DOCUMENTS)
    now = datetime.now(timezone.utc)
    return ConversationSummary.model_validate(
        SimpleNamespace(id=uuid4(), appointment_id=uuid4(), created_at=now, updated_at=now, **payload)
    )


@pytest.mark.asyncio
async def test_t9_comprehensive_does_not_fall_back_to_fhir_for_the_new_outcome():
    from src.app.services.summarization.comprehensive_summarization import ComprehensiveSummarizationService

    service = ComprehensiveSummarizationService.__new__(ComprehensiveSummarizationService)
    row = _new_row_summary()
    service._run_attachment_summarization = AsyncMock(return_value=row)
    service._run_fhir_analysis = AsyncMock(side_effect=AssertionError("must not fall back to FHIR"))
    assert await service._run_attachment_with_fhir_fallback(SimpleNamespace()) is row


@pytest.mark.asyncio
async def test_t9_verified_cache_never_serves_the_new_outcome():
    from src.app.services.summary_cache import verified_attachment_cache

    meta = _static_fallback_summary_data(_request(), _appointment(), "Dr. X", state=NO_VISIT_SUMMARY_DOCUMENTS)["summary_metadata"]
    meta["source_fingerprint"] = "fp"  # even if a fingerprint were somehow present
    repo = SimpleNamespace(
        get_by_appointment_id_and_source=AsyncMock(return_value=SimpleNamespace(user_id="u", summary_metadata=meta))
    )
    request = SimpleNamespace(user_id="u", appointment_id=uuid4(), force_regenerate=False)
    assert await verified_attachment_cache(repo, request, "fp") is None


# ---------------------------------------------------------------------------------------------
# T12: sync route contract
# ---------------------------------------------------------------------------------------------
def test_t12_sync_route_serializes_summary_metadata_key(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.app.db.config.database import get_db
    from src.app.routes import care_capture

    row = _new_row_summary()

    class FakeService:
        def __init__(self, db):
            pass

        async def analyze_attachments(self, request):
            return row

    app = FastAPI()
    app.include_router(care_capture.router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    monkeypatch.setattr(care_capture, "AttachmentSummarizationService", FakeService)
    monkeypatch.setattr(care_capture, "authorize_summary_scope", AsyncMock())
    response = TestClient(app).post(
        "/care-capture/attachment-summary", json={"appointment_id": str(uuid4()), "user_id": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summaryMetadata"]["processing_outcome"] == "no_visit_summary_documents"
    assert body["summaryMetadata"]["is_clinical_summary"] is False
    assert "metadata" not in body
    assert body["summaryText"] == EXPECTED_MESSAGE
