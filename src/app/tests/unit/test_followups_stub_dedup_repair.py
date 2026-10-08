"""Follow-up fixes: diagnosis-wording repair issues, per-batch reason preservation, stub-document
skipping, parsed-text dedup, historical-procedure demotion, parser warm-up."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.app.chains.attachment_summarization import chain as chain_mod
from src.app.chains.attachment_summarization.chain import (
    AttachmentSummarizationChain,
    _diagnosis_repair_issues,
    _split_procedures,
)
from src.app.models.attachment_summarization import (
    AttachmentSummarizationRequest,
    DiagnosisDetail,
    DocumentAttachment,
    DocumentSummary,
    ProcedureMention,
)
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ingestion import (
    drop_parsed_text_duplicates,
    mark_parsed,
    process_attachments,
    split_stub_documents,
)
from src.app.services.stub_documents import stub_reason

SOURCE = "Assessment\nAnticoagulation/antiplatelist: continue aspirin\nHypertension, essential\n"


def _doc(text, rid="d1", ctype="text/html", error=None):
    return DocumentAttachment(
        file_path="p",
        content_type=ctype,
        extracted_text=text,
        resource_id=rid,
        extraction_error=error,
    )


def _summary(diagnoses, rid="d1"):
    return DocumentSummary(
        source_document_id=rid,
        evidence_quotes=["Hypertension, essential"],
        source_document_title="t",
        source_document_type="note",
        narrative_summary="n",
        diagnoses=[
            DiagnosisDetail(official_diagnosis=d, lay_explanation="") for d in diagnoses
        ],
    )


# ---- item 1 -------------------------------------------------------------------------------
def test_repair_issues_carry_failing_diagnosis_and_closest_line():
    issues = _diagnosis_repair_issues(["Anticoagulation therapy"], SOURCE)
    assert issues[0]["failing_diagnosis"] == "Anticoagulation therapy"
    assert any(
        "Anticoagulation/antiplatelist" in line
        for line in issues[0]["closest_source_lines"]
    )
    assert "VERBATIM" in issues[0]["instruction"]


@pytest.mark.asyncio
async def test_gate_still_fails_closed_and_repair_prompt_gets_issue(monkeypatch):
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
    chain._extraction_agent = SimpleNamespace(run=None)
    prompts = []

    async def fake_model_call(run, prompt):
        prompts.append(prompt)
        return SimpleNamespace(output=[_summary(["Anticoagulation therapy"])])

    monkeypatch.setattr(chain_mod, "model_call", fake_model_call)
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(SOURCE)], 1, 1)
    assert info.value.reason_code == "DIAGNOSIS_WORDING_NOT_GROUNDED"
    assert len(prompts) == 2  # exactly one repair attempt
    assert (
        "Anticoagulation therapy" in prompts[1] and "closest_source_lines" in prompts[1]
    )
    assert "failing_diagnosis" not in prompts[0]


# ---- item 2 -------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_batches_failed_keeps_specific_reason(monkeypatch):
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)

    async def boom(batch, i, n):
        raise DocumentProcessingError("DIAGNOSIS_WORDING_NOT_GROUNDED")

    monkeypatch.setattr(chain, "_extract_batch", boom, raising=False)
    with pytest.raises(DocumentProcessingError) as info:
        await chain._analyze(
            {},
            [
                mark_parsed(_doc("some clinical text here", "a")),
                mark_parsed(_doc("other text", "b")),
            ],
        )
    assert (
        info.value.code == "CLINICAL_EVIDENCE_FAILED"
    )  # persisted canonical code unchanged
    assert info.value.reason_code == "DIAGNOSIS_WORDING_NOT_GROUNDED"
    assert sum(info.value.batch_reason_counts.values()) >= 1


def test_specific_reason_reaches_processing_errors():
    from src.app.services.summary_outcomes import outcome_metadata

    meta = outcome_metadata(
        "unavailable",
        [
            {
                "error": "CLINICAL_EVIDENCE_FAILED",
                "reason": "DIAGNOSIS_WORDING_NOT_GROUNDED",
            }
        ],
    )
    assert meta["processing_errors"][0]["error"] == "CLINICAL_EVIDENCE_FAILED"
    assert meta["processing_errors"][0]["reason"] == "DIAGNOSIS_WORDING_NOT_GROUNDED"


# ---- item 4 -------------------------------------------------------------------------------
def _proc(desc, status, section):
    return ProcedureMention(
        source_quote=desc, description=desc, status=status, source_section=section
    )


def test_historical_ordered_procedure_not_in_recommendations():
    summary = _summary([])
    summary.procedures = [
        _proc("Appendectomy 1998", "ordered", "Surgical History"),
        _proc("History of cholecystectomy", "ordered", None),
        _proc("Colonoscopy referral", "ordered", "Plan of Treatment"),
    ]
    record = _split_procedures([summary])[0]
    assert record["procedures_ordered"] == ["Colonoscopy referral"]
    assert record["procedures_not_stated"] == [
        "Appendectomy 1998",
        "History of cholecystectomy",
    ]


def test_prompts_forbid_historical_recommendations():
    assert "NEVER put past/historical items here" in chain_mod._EXTRACTION_SYSTEM_PROMPT
    assert "HISTORICAL" in chain_mod._EXTRACTION_SYSTEM_PROMPT


# ---- item 5 -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "test note",
        "Test Note",
        "asdf",
        "Page: 1 of 1",
        "  \n",
        "Page: 1 of 1\n\nPage: 1 of 1",
        "testing",
        "Patient: Jane Doe  DOB: 1970-01-01\nProvider: Dr X\n*** The external document could not be loaded. ***\nPage: 1 of 1",
    ],
)
def test_stub_texts_detected(text):
    assert stub_reason(text)


def test_cerner_header_only_printouts_detected():
    head = "[Page 1]\n Model Clinic 1\nPatient: SMART, Harry\nProgress Notes\nDocument Type: Neurology Progress Note\n"
    sign = "Sign Information: SYSTEM,SYSTEM Cerner (1/24/2025 05:58 CST)\n"
    tail = "Electronically Signed on 01/24/25\nReport Request ID: 1  Page 1 of 1  Print Date/Time: 10/5/2026\n"
    assert stub_reason(head + sign + tail) == "header_only"
    assert stub_reason(
        head + sign + "   *** The external document could not be loaded. ***\n" + tail
    )
    assert (
        stub_reason(
            head
            + sign
            + "Patient seen for chest pain. Start metoprolol 25 mg daily.\n"
            + tail
        )
        is None
    )



@pytest.mark.parametrize(
    "text",
    [
        "Hypertension",
        "Patient doing well. Continue lisinopril 10 mg daily.",
        "BP 120/80. Follow up in 6 weeks.",
        "Test results: hemoglobin A1c 6.1%, within goal.",
        "Assessment: type 2 diabetes mellitus\nPage: 1 of 2",
        "Note: external document attached; reviewed. "
        + "Patient reports chest pain. " * 200,
    ],
)
def test_real_clinical_text_survives(text):
    assert stub_reason(text) is None


def test_split_stub_documents_keeps_real_and_errors():
    docs = [
        _doc("test note", "a"),
        _doc("Patient has hypertension.", "b"),
        _doc("", "c", error="PARSER_TIMEOUT"),
    ]
    kept, reasons = split_stub_documents(docs)
    assert [d.resource_id for d in kept] == ["b", "c"] and reasons == {"placeholder": 1}


def test_stub_flag_defaults_on_and_not_overridable():
    from src.app.core.settings import Settings
    from src.app.config.ssm_loader import SSMParameterLoader

    assert Settings.model_fields["SKIP_STUB_DOCUMENTS_ENABLED"].default is True
    assert Settings.model_fields["PARSED_TEXT_DEDUP_ENABLED"].default is True
    import inspect

    assert "SKIP_STUB_DOCUMENTS_ENABLED" not in inspect.getsource(SSMParameterLoader)


@pytest.mark.asyncio
async def test_stub_only_appointment_takes_zero_model_call_path(monkeypatch):
    from src.app.tests.unit.test_attachment_summarization_no_visit_summary_documents import (
        _request,
        _service,
        _wire,
    )

    service = _service(selection=None, candidates=False)

    async def stubs(refs):
        return [_doc("test note", "a"), _doc("asdf", "b"), _doc("Page: 1 of 1", "c")]

    service._process_attachments = stubs
    ref = SimpleNamespace(ehr_resource_id="r1", data={}, updated_at="x")
    _wire(monkeypatch, service, [ref])
    await service.analyze_attachments(_request())
    assert service.llm_work == []
    meta = service.summaries_repo.upsert_calls[0][1]["summary_metadata"]
    assert meta["processing_outcome"] == "no_visit_summary_documents"
    assert any("stub_documents_skipped" in m for m in service.logs)


@pytest.mark.asyncio
async def test_stub_flag_off_restores_old_path(monkeypatch):
    from src.app.tests.unit.test_attachment_summarization_no_visit_summary_documents import (
        _request,
        _service,
        _wire,
    )
    from src.app.core.settings import get_settings

    monkeypatch.setattr(get_settings(), "SKIP_STUB_DOCUMENTS_ENABLED", False)
    service = _service(selection=None, candidates=False)

    async def stubs(refs):
        return [_doc("test note", "a")]

    service._process_attachments = stubs
    _wire(
        monkeypatch,
        service,
        [SimpleNamespace(ehr_resource_id="r1", data={}, updated_at="x")],
    )
    await service.analyze_attachments(_request())
    assert service.llm_work == ["called"]  # reached AI analysis as before the change


# ---- item 6 -------------------------------------------------------------------------------
def test_parsed_text_dedup_keeps_preferred_format_and_normalizes_whitespace():
    docs = [
        _doc("Same   note\ntext", "pdf", "application/pdf"),
        _doc("same note text", "html", "text/html"),
        _doc("different note", "other", "text/html"),
        _doc("", "err", "text/html", error="PARSER_TIMEOUT"),
    ]
    kept = drop_parsed_text_duplicates(docs)
    assert [d.resource_id for d in kept] == ["html", "other", "err"]


@pytest.mark.asyncio
async def test_process_attachments_dedups_on_parsed_text():
    class Storage:
        async def download_document(self, path):
            return path.encode()

    class Extractor:
        MAX_FILE_SIZE = 10**7

        async def extract_text_async(self, content, ctype, name=None):
            return "Identical clinical note text"

    def ref(rid, path):
        att = {
            "filePath": path,
            "checksum": path,
            "downloadStatus": "success",
            "contentType": "text/html",
            "title": "t",
        }
        return SimpleNamespace(
            ehr_resource_id=rid, data={"attachments": [att], "type": "Note"}
        )

    out = await process_attachments(
        [ref("r1", "a"), ref("r2", "b")], Storage(), Extractor()
    )
    assert len(out) == 1


# ---- item 3 -------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parser_warmup_never_raises(monkeypatch):
    from src.app.services import parser_warmup

    async def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(parser_warmup, "_run", boom)
    await parser_warmup.warm_up_parsers()


@pytest.mark.asyncio
async def test_parser_warmup_parses_all_three_samples():
    from src.app.services import parser_warmup

    assert await parser_warmup._run() == ["pdf", "html", "xml"]
