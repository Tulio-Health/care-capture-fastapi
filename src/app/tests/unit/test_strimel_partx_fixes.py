"""Strimel summary-regression fixes X1-X6 (each behind its own settings flag, default OFF)."""

from types import SimpleNamespace

import pytest

from src.app.chains.attachment_summarization import chain as chain_mod
from src.app.chains.attachment_summarization.chain import (
    AttachmentSummarizationChain,
    _check_medication_doses,
    _clean_lab_results,
    _clean_recommendation,
    _split_batch,
    _structured_completed_anchor,
)
from src.app.core.settings import get_settings
from src.app.models.attachment_summarization import (
    DiagnosisDetail,
    DocumentAttachment,
    DocumentSummary,
    ProcedureMention,
)
from src.app.services.document_extraction import DocumentProcessingError, DocumentTextExtractor
from src.app.services.summary_runtime import model_error_code

SOURCE = "Assessment\nAnticoagulation/antiplatelist: continue aspirin\nHypertension, essential\n"
FLAGS = ("DROP_UNGROUNDED_ANCHORS_ENABLED", "MEDICATION_RETENTION_ENABLED", "EVIDENCE_REPAIR_HINTS_ENABLED", "PROCEDURE_STATUS_V2_ENABLED", "CDA_COMPACT_EXTRACTION_ENABLED", "EXTRACTION_TRUNCATION_SPLIT_ENABLED",
         "DROP_UNGROUNDED_DIAGNOSIS_ENABLED", "SUMMARY_CLUTTER_FILTER_ENABLED", "MEDICATION_DOSE_CHECK_ENABLED")


@pytest.fixture
def flags(monkeypatch):
    def set_(**values):
        for name, value in values.items():
            monkeypatch.setattr(get_settings(), name, value)
    return set_


def _doc(text, rid="d1", title="Note", doc_type="Progress Note"):
    return DocumentAttachment(file_path="p", content_type="text/html", extracted_text=text,
                              resource_id=rid, title=title, document_type=doc_type)


def _summary(rid="d1", diagnoses=(), procedures=(), medications=(), evidence=("Hypertension, essential",)):
    return DocumentSummary(
        source_document_id=rid, evidence_quotes=list(evidence), source_document_title="t",
        source_document_type="note", narrative_summary="n",
        diagnoses=[DiagnosisDetail(official_diagnosis=d, lay_explanation="") for d in diagnoses],
        procedures=list(procedures), medications=list(medications))


def _chain(monkeypatch, outputs):
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
    chain._extraction_agent = SimpleNamespace(run=None)
    prompts = []

    async def fake_model_call(run, prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(output=[outputs[min(len(prompts), len(outputs)) - 1]],
                               usage=lambda: None, all_messages=lambda: [])

    async def no_verify(*a, **k):
        return None

    monkeypatch.setattr(chain_mod, "model_call", fake_model_call)
    monkeypatch.setattr(chain, "_verify_stage", no_verify, raising=False)
    return chain, prompts


def test_x3_extraction_timeout_default_unchanged_and_clamped(flags):
    from src.app.services.summary_runtime import MODEL_CALL_TIMEOUT_S, extraction_call_timeout_s
    assert extraction_call_timeout_s() == MODEL_CALL_TIMEOUT_S == 45
    flags(EXTRACTION_CALL_TIMEOUT_S=90)
    assert extraction_call_timeout_s() == 90
    flags(EXTRACTION_CALL_TIMEOUT_S=999)
    assert extraction_call_timeout_s() == 120


def test_all_flags_default_off():
    from src.app.core.settings import Settings
    for name in FLAGS:
        assert Settings.model_fields[name].default is False, name


# ---- X4 ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_x4_ungrounded_diagnosis_dropped_after_repair_never_kept(monkeypatch, flags):
    flags(DROP_UNGROUNDED_DIAGNOSIS_ENABLED=True)
    bad = _summary(diagnoses=["Anticoagulation therapy", "Hypertension, essential"])
    chain, prompts = _chain(monkeypatch, [bad, _summary(diagnoses=["Anticoagulation therapy", "Hypertension, essential"])])
    out = await chain._extract_batch([_doc(SOURCE)], 1, 1)
    assert len(prompts) == 2  # the first attempt still fails closed into the repair
    assert [d.official_diagnosis for d in out[0].diagnoses] == ["Hypertension, essential"]


@pytest.mark.asyncio
async def test_x4_flag_off_still_fails_closed(monkeypatch, flags):
    flags(DROP_UNGROUNDED_DIAGNOSIS_ENABLED=False)
    chain, _ = _chain(monkeypatch, [_summary(diagnoses=["Anticoagulation therapy"])])
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(SOURCE)], 1, 1)
    assert info.value.reason_code == "DIAGNOSIS_WORDING_NOT_GROUNDED"


# ---- X1 ------------------------------------------------------------------------------------
OP_SOURCE = "Procedure: Microdissection testicular sperm extraction [55870]\nAnesthesia: general\n"


def _proc(quote, status="performed", desc=None):
    return ProcedureMention(source_quote=quote, description=desc or quote, status=status, source_section=None)


@pytest.mark.asyncio
async def test_x1_operative_note_header_anchor_accepted(monkeypatch, flags):
    flags(PROCEDURE_STATUS_V2_ENABLED=True)
    q = "Procedure: Microdissection testicular sperm extraction [55870]"
    chain, _ = _chain(monkeypatch, [_summary(evidence=[q], procedures=[_proc(q)])])
    out = await chain._extract_batch([_doc(OP_SOURCE, title="Op Note", doc_type="Op Note")], 1, 1)
    assert out[0].procedures[0].status == "performed"


@pytest.mark.asyncio
async def test_x1_contradicted_anchor_still_raises(monkeypatch, flags):
    flags(PROCEDURE_STATUS_V2_ENABLED=True)
    src = "Plan: MRI lumbar spine ordered for next week\n"
    q = "MRI lumbar spine ordered for next week"
    chain, _ = _chain(monkeypatch, [_summary(evidence=[q], procedures=[_proc(q)])])
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(src, title="Op Note", doc_type="Op Note")], 1, 1)
    assert info.value.reason_code == "PROCEDURE_STATUS_NOT_GROUNDED"


@pytest.mark.asyncio
async def test_x1_no_verb_non_operative_is_demoted_not_failed(monkeypatch, flags):
    flags(PROCEDURE_STATUS_V2_ENABLED=True)
    src = "Surgical history\nAppendectomy 2010\n"
    chain, _ = _chain(monkeypatch, [_summary(evidence=["Appendectomy 2010"], procedures=[_proc("Appendectomy 2010")])])
    out = await chain._extract_batch([_doc(src)], 1, 1)
    assert out[0].procedures[0].status == "not_stated"


def test_x1_xml_status_completed_is_performed_evidence_but_markers_are_not():
    line = "procedure | code: Colonoscopy (45378) | statusCode: completed | effectiveTime: 20221007"
    assert _structured_completed_anchor("Colonoscopy (45378)", line)
    assert _structured_completed_anchor("Colonoscopy", "ClinicalDocument/x/procedure/statusCode: code=completed Colonoscopy")
    assert not _structured_completed_anchor("Colonoscopy (45378)", "[ORDERED/PLANNED] " + line)
    assert not _structured_completed_anchor("Colonoscopy (45378)", "NEGATED: " + line)
    assert not _structured_completed_anchor("Colonoscopy (45378)", line.replace("completed", "active"))


@pytest.mark.asyncio
async def test_x1_flag_off_keeps_old_gate(monkeypatch, flags):
    flags(PROCEDURE_STATUS_V2_ENABLED=False)
    q = "Procedure: Microdissection testicular sperm extraction [55870]"
    chain, _ = _chain(monkeypatch, [_summary(evidence=[q], procedures=[_proc(q)])])
    with pytest.raises(DocumentProcessingError):
        await chain._extract_batch([_doc(OP_SOURCE, title="Op Note", doc_type="Op Note")], 1, 1)


# ---- X3 ------------------------------------------------------------------------------------
def test_x3_incomplete_tool_call_classified_truncated_only_with_flag(flags):
    from pydantic_ai.exceptions import IncompleteToolCall
    flags(EXTRACTION_TRUNCATION_SPLIT_ENABLED=False)
    assert model_error_code(IncompleteToolCall("x")) == "MODEL_UNAVAILABLE"
    flags(EXTRACTION_TRUNCATION_SPLIT_ENABLED=True)
    assert model_error_code(IncompleteToolCall("x")) == "MODEL_OUTPUT_TRUNCATED"
    exc = DocumentProcessingError("MODEL_OUTPUT_TRUNCATED")
    assert exc.code == "MODEL_OUTPUT_INVALID" and exc.reason_code == "MODEL_OUTPUT_TRUNCATED"


def test_x3_split_halves_are_verbatim_and_cover_the_chunk():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    doc = _doc(text, rid="doc9:chunk:1000")
    halves = _split_batch([doc])
    a, b = halves[0][0], halves[1][0]
    assert a.extracted_text in text and b.extracted_text in text
    assert a.resource_id == "doc9:chunk:1000"
    off = int(b.resource_id.rsplit(":chunk:", 1)[1]) - 1000
    assert text[off:off + len(b.extracted_text)] == b.extracted_text
    assert off < len(a.extracted_text)  # overlapping, no gap
    assert b.extracted_text.endswith(text.rstrip()[-20:])


@pytest.mark.asyncio
async def test_x3_truncated_chunk_is_split_once(monkeypatch, flags):
    flags(EXTRACTION_TRUNCATION_SPLIT_ENABLED=True)
    text = "\n".join(f"Hypertension, essential {i} " + "y" * 40 for i in range(150))
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
    calls = []

    async def attempt(batch, n, total, notes=None):
        calls.append(batch[0].resource_id)
        if len(calls) == 1:
            raise DocumentProcessingError("MODEL_OUTPUT_TRUNCATED")
        return [_summary(rid=batch[0].resource_id)]

    monkeypatch.setattr(chain, "_extract_batch_attempt", attempt, raising=False)
    out = await chain._extract_batch([_doc(text, rid="d:chunk:0")], 1, 1)
    assert len(calls) == 3 and len(out) == 2


# ---- X5 ------------------------------------------------------------------------------------
def test_x5_vitals_and_order_only_entries_leave_labs():
    labs = ["Temperature: 98.6 F", "Blood Pressure: 124/73", "WBC: 12.1 x10E3/uL (3.4 - 10.8)",
            "Ferritin: Ordered", "Pulse: 65", "SpO2: 98%", "TSH: 1.460 uIU/mL", "BMI: 28.04"]
    assert _clean_lab_results(labs) == ["WBC: 12.1 x10E3/uL (3.4 - 10.8)", "TSH: 1.460 uIU/mL"]


def test_x5_orders_scaffolding_cleaned():
    assert _clean_recommendation("Orders: \u2022 CBC \u2022 Ferritin") == "Ordered: CBC; Ferritin"
    assert _clean_recommendation("Use saline spray twice daily") == "Use saline spray twice daily"
    assert _clean_recommendation("Orders:") == ""


# ---- X6 ------------------------------------------------------------------------------------
DOSE_SRC = "Medications\namoxicillin-clavulanate 875-125 mg tablet: take 1 tablet twice daily for 5 days\n"


def test_x6_grounded_dose_kept_ungrounded_dose_stripped():
    meds = ["amoxicillin-clavulanate 875-125 mg tablet twice daily",
            "amoxicillin-clavulanate 500 mg every 12 hours"]
    out = _check_medication_doses(meds, DOSE_SRC)
    assert out[0] == meds[0]
    assert "500" not in out[1] and out[1].startswith("amoxicillin-clavulanate")


def test_x6_fabricated_drug_with_dose_dropped():
    assert _check_medication_doses(["warfarin 5 mg daily"], DOSE_SRC) == []


def test_x6_dose_spacing_and_case_insensitive():
    assert _check_medication_doses(["Amoxicillin-Clavulanate 875-125MG"], DOSE_SRC) == ["Amoxicillin-Clavulanate 875-125MG"]


# ---- X2 ------------------------------------------------------------------------------------
CDA = b"""<?xml version="1.0"?>
<ClinicalDocument xmlns="urn:hl7-org:v3"><title>Summary</title>
<recordTarget><patientRole><patient><name><given>A</given></name></patient></patientRole></recordTarget>
<component><structuredBody><component><section><title>Medications</title>
<text><table><tbody><tr><td ID="med1">losartan 25 MG tablet</td><td>Take 25 mg daily</td></tr></tbody></table></text>
<entry><substanceAdministration classCode="SBADM" moodCode="INT"><statusCode code="active"/>
<doseQuantity value="25" unit="mg"/><consumable><manufacturedProduct><manufacturedMaterial>
<code code="979485"><originalText><reference value="#med1"/></originalText></code></manufacturedMaterial></manufacturedProduct></consumable>
<author><time value="20221007"/><assignedAuthor><addr><city>X</city></addr></assignedAuthor></author>
</substanceAdministration></entry>
<entry><procedure moodCode="EVN"><code code="55870" displayName="Sperm extraction"/><statusCode code="completed"/>
<effectiveTime value="20221007"/></procedure></entry>
<entry><observation moodCode="EVN" negationInd="true"><code displayName="Fever"/><statusCode code="completed"/></observation></entry>
</section></component></structuredBody></component></ClinicalDocument>"""


def test_x2_flag_off_is_strict7_and_unchanged(flags):
    flags(CDA_COMPACT_EXTRACTION_ENABLED=False)
    assert DocumentTextExtractor.VERSION == "strict-7"
    assert "@ " in DocumentTextExtractor._xml_text(CDA) or "/" in DocumentTextExtractor._xml_text(CDA)


def test_x2_compact_one_line_per_statement_keeps_values_and_markers(flags):
    flags(CDA_COMPACT_EXTRACTION_ENABLED=True)
    assert DocumentTextExtractor.VERSION == "strict-8"
    text = DocumentTextExtractor._xml_text(CDA)
    lines = text.splitlines()
    med = [l for l in lines if "substanceAdministration" in l]
    assert len(med) == 1 and med[0].startswith("[ORDERED/PLANNED]")
    assert "25 mg" in med[0] and "979485" in med[0] and "losartan 25 MG tablet" in med[0]
    proc = [l for l in lines if l.startswith("procedure")]
    assert proc and "Sperm extraction (55870)" in proc[0] and "statusCode: completed" in proc[0]
    assert any(l.startswith("NEGATED: observation") and "Fever" in l for l in lines)
    assert "losartan 25 MG tablet: Take 25 mg daily" in text  # narrative row unchanged
    assert "\nA\n" in text  # header kept (strict-7 walk)
    assert "city" not in text and "\nX\n" not in text  # entry author/addr plumbing dropped


# ---- X3b / X5b -----------------------------------------------------------------------------
def test_x3b_trailing_period_trimmed_only_on_exact_containment():
    from src.app.chains.attachment_summarization.chain import _trim_terminal_punctuation as trim
    src = "Plan: Call if symptoms persist or worsen, new fever, or rash\nNegative"
    assert trim("Call if symptoms persist or worsen, new fever.", src) == "Call if symptoms persist or worsen, new fever"
    assert trim("Call if symptoms persist or worsen, new rash.", src).endswith(".")  # not in source
    assert trim("Negative.", src) == "Negative."  # too short to trim


@pytest.mark.asyncio
async def test_x5b_record_medications_retained(monkeypatch, flags):
    from src.app.models.attachment_summarization import AttachmentSummarizationResponse
    flags(MEDICATION_RETENTION_ENABLED=True, MEDICATION_DOSE_CHECK_ENABLED=True)
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
    chain._synthesis_agent = SimpleNamespace(run=None)
    resp = AttachmentSummarizationResponse.model_construct(
        clinical_summary="s", key_insights=[], diagnoses_mentioned=[], procedures_mentioned=[],
        medications_mentioned=["Losartan daily"], lab_results=[], instructions=[], follow_up=[],
        recommendations=[], risk_factors=[], document_metadata=[], extraction_errors=[])

    async def fake_model_call(run, prompt, **k):
        return SimpleNamespace(output=resp)

    async def no_verify(*a, **k):
        return None

    monkeypatch.setattr(chain_mod, "model_call", fake_model_call)
    monkeypatch.setattr(chain, "_verify_stage", no_verify, raising=False)
    records = [{"medications": ["losartan 25 MG tablet daily", "omeprazole 40 MG capsule"], "procedures_performed": []}]
    out = await chain._synthesize_records_attempt({}, records, 1)
    assert out.medications_mentioned == ["Losartan daily", "omeprazole 40 MG capsule"]


def test_x3b_composite_quote_keeps_only_supported_pieces():
    from src.app.chains.attachment_summarization.chain import _supported_quote_pieces
    src = "HPI\nCongestion over 1 week\nFrontal headache > x 2 days\nPlan | Flonase nasal spray daily"
    quote = "Congestion over 1 week. Frontal headache > x 2 days. The patient was admitted to the ICU overnight."
    assert _supported_quote_pieces(quote, src) == ["Congestion over 1 week", "Frontal headache > x 2 days"]
    assert _supported_quote_pieces("The patient was admitted to the ICU. Intubated for septic shock.", src) == []


# ---- X4b -----------------------------------------------------------------------------------
from src.app.models.attachment_summarization import FollowUpDetail  # noqa: E402

ANCHOR_SRC = ("Assessment & Plan\nHypertension, essential\nOrders: \u2022 FLU A B (Rapid Molecular - Office)\n"
              "Return in 2 weeks for blood pressure check\nColonoscopy completed 03/02/2021\n")


def _fu(quote, text="Return visit"):
    return FollowUpDetail(follow_up=text, source_quote=quote)


@pytest.mark.asyncio
async def test_x4b_unsupported_anchor_dropped_after_repair_rest_kept(monkeypatch, flags):
    flags(DROP_UNGROUNDED_ANCHORS_ENABLED=True)
    bad_proc = _proc("Orders: FLU A B Rapid Molecular Office, nasal swab sent", status="ordered")
    good_fu = _fu("Return in 2 weeks for blood pressure check")
    s = lambda: _summary(diagnoses=["Hypertension, essential"], procedures=[bad_proc], evidence=["Hypertension, essential"])
    s1, s2 = s(), s()
    s2.follow_up = [good_fu, _fu("Return in 6 months for MRI of the brain")]
    chain, prompts = _chain(monkeypatch, [s1, s2])
    out = await chain._extract_batch([_doc(ANCHOR_SRC)], 1, 1)
    assert len(prompts) == 2  # first attempt still fails closed
    assert out[0].procedures == []
    assert [f.source_quote for f in out[0].follow_up] == ["Return in 2 weeks for blood pressure check"]
    assert [d.official_diagnosis for d in out[0].diagnoses] == ["Hypertension, essential"]


@pytest.mark.asyncio
async def test_x4b_fabricated_wrong_date_negated_items_never_kept(monkeypatch, flags):
    flags(DROP_UNGROUNDED_ANCHORS_ENABLED=True)
    items = [_proc("Colonoscopy completed 03/09/2021"),            # wrong date
             _proc("Colonoscopy not completed 03/02/2021"),        # negation flip
             _proc("Cardiac catheterization performed 03/02/2021")]  # fabricated
    s = lambda: _summary(diagnoses=["Hypertension, essential"], procedures=list(items), evidence=["Hypertension, essential"])
    chain, _ = _chain(monkeypatch, [s(), s()])
    out = await chain._extract_batch([_doc(ANCHOR_SRC)], 1, 1)
    assert out[0].procedures == []


@pytest.mark.asyncio
async def test_x4b_supported_but_contradicted_status_still_fails(monkeypatch, flags):
    flags(DROP_UNGROUNDED_ANCHORS_ENABLED=True, PROCEDURE_STATUS_V2_ENABLED=True)
    src = "Plan\nMRI lumbar spine ordered for next week\n"
    q = "MRI lumbar spine ordered for next week"
    chain, _ = _chain(monkeypatch, [_summary(evidence=[q], procedures=[_proc(q)])])
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(src)], 1, 1)
    assert info.value.reason_code == "PROCEDURE_STATUS_NOT_GROUNDED"


@pytest.mark.asyncio
async def test_x4b_flag_off_unsupported_anchor_still_fails_chunk(monkeypatch, flags):
    flags(DROP_UNGROUNDED_ANCHORS_ENABLED=False)
    s = lambda: _summary(procedures=[_proc("Cardiac catheterization performed 03/02/2021")])
    chain, _ = _chain(monkeypatch, [s(), s()])
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(ANCHOR_SRC)], 1, 1)
    assert info.value.reason_code == "INVALID_SOURCE_EVIDENCE"
