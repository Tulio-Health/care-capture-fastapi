"""Strimel Part X round 3: X6 v2 dose layouts, X7 label fixes, X8 deterministic post-checks,
X9 evidence fallback to verified anchors, X10 split on exhausted output validation."""

from types import SimpleNamespace

import pytest

from src.app.chains.attachment_summarization import chain as chain_mod
from src.app.chains.attachment_summarization.chain import (
    AttachmentSummarizationChain,
    _anchor_evidence_fallback,
    _check_medication_doses,
    _deterministic_post_checks,
    _normalize_medications,
    _past_procedure_items,
    _split_procedures,
)
from src.app.core.settings import Settings, get_settings
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DiagnosisDetail,
    DocumentAttachment,
    DocumentSummary,
    ProcedureMention,
)
from src.app.services.document_extraction import DocumentProcessingError

SOURCE = "Assessment\nAnticoagulation/antiplatelist: continue aspirin\nHypertension, essential\n"
ROUND3 = ("EVIDENCE_FALLBACK_ENABLED", "SUMMARY_LABEL_FIXES_ENABLED", "MEDICATION_DOSE_CHECK_V2_ENABLED",
          "MEDICATION_NAME_CHECK_ENABLED", "SUMMARY_DATE_CHECK_ENABLED", "EXTRACTION_INVALID_SPLIT_ENABLED")


@pytest.fixture
def flags(monkeypatch):
    def set_(**values):
        for name, value in values.items():
            monkeypatch.setattr(get_settings(), name, value)
    return set_


def _doc(text, rid="d1"):
    return DocumentAttachment(file_path="p", content_type="text/html", extracted_text=text, resource_id=rid,
                              title="Note", document_type="Progress Note")


def _summary(rid="d1", diagnoses=(), procedures=(), medications=(), evidence=("Hypertension, essential",)):
    return DocumentSummary(
        source_document_id=rid, evidence_quotes=list(evidence), source_document_title="t",
        source_document_type="note", narrative_summary="n",
        diagnoses=[DiagnosisDetail(official_diagnosis=d, lay_explanation="") for d in diagnoses],
        procedures=list(procedures), medications=list(medications))


def _proc(quote, status="performed"):
    return ProcedureMention(source_quote=quote, description=quote, status=status, source_section=None)


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


def test_round3_flags_default_off():
    for name in ROUND3:
        assert Settings.model_fields[name].default is False, name


# ---- X6 v2 ---------------------------------------------------------------------------------
def test_x6v2_rate_after_comma_and_equivalent_layouts(flags):
    src = "sodium chloride 0.9 % KVO, 0-10 mL/hr, intraVENOUS\namoxicillin-clavulanate 875-125 mg tablet"
    flags(MEDICATION_DOSE_CHECK_V2_ENABLED=True)
    assert _check_medication_doses(["sodium chloride 0.9 % KVO, 0-10 mL/hr"], src) == ["sodium chloride 0.9 % KVO, 0-10 mL/hr"]
    assert _check_medication_doses(["amoxicillin-clavulanate 875/125 mg"], src) == ["amoxicillin-clavulanate 875/125 mg"]
    assert "500" not in _check_medication_doses(["amoxicillin-clavulanate 500/125 mg"], src)[0]
    assert "25 mg" not in _check_medication_doses(["amoxicillin-clavulanate 25 mg"], src)[0]  # not inside "125 mg"
    flags(MEDICATION_DOSE_CHECK_V2_ENABLED=False)
    assert "0-10" not in _check_medication_doses(["sodium chloride 0.9 % KVO, 0-10 mL/hr"], src)[0]  # v1 over-strip


# ---- X7 ------------------------------------------------------------------------------------
def test_x7_past_procedures_exclude_orders_this_visit_and_titles():
    items = ["Orders: \u2022 FLU A B (Rapid Molecular - Office)", "Biopsy Testis Incisional (Right)",
             "Surgical Sperm Extraction Post-operative Instructions", "Vasectomy 2015"]
    assert _past_procedure_items(items, ["Biopsy Testis Incisional (Right)"], []) == ["Vasectomy 2015"]


def test_x7_medications_split_or_and_dedup():
    src = "Tylenol or motrin prn pain/fever\nFlonase nasal spray"
    out = _normalize_medications(["Tylenol or Motrin as needed for pain/fever", "Motrin", "Flonase nasal spray",
                                  "flonase nasal spray."], src)
    assert out == ["Tylenol as needed for pain/fever", "Motrin as needed for pain/fever", "Flonase nasal spray"]
    assert _normalize_medications(["Tylenol or Warfarin daily"], src) == ["Tylenol or Warfarin daily"]


def test_x7_order_line_never_performed(flags):
    flags(SUMMARY_LABEL_FIXES_ENABLED=True)
    rec = _split_procedures([_summary(procedures=[_proc("Orders: \u2022 FLU A B (Rapid Molecular - Office)", "not_stated")])])[0]
    assert rec["procedures_performed"] == [] and rec["procedures_not_stated"] == []
    assert rec["procedures_ordered"] == ["Orders: \u2022 FLU A B (Rapid Molecular - Office)"]


@pytest.mark.asyncio
async def test_x7_procedure_not_a_diagnosis_and_past_procedures_clean(monkeypatch, flags):
    flags(SUMMARY_LABEL_FIXES_ENABLED=True)
    chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
    chain._synthesis_agent = SimpleNamespace(run=None)
    resp = AttachmentSummarizationResponse.model_construct(
        clinical_summary="s", key_insights=[], procedures_mentioned=["Biopsy Testis Incisional (Right)"],
        diagnoses_mentioned=[DiagnosisDetail(official_diagnosis="surgical sperm extraction", lay_explanation=""),
                             DiagnosisDetail(official_diagnosis="Azoospermia", lay_explanation="")],
        medications_mentioned=[], lab_results=[], instructions=[], follow_up=[], recommendations=[],
        risk_factors=[], document_metadata=[], extraction_errors=[])

    async def fake_model_call(run, prompt, **k):
        return SimpleNamespace(output=resp)

    async def no_verify(*a, **k):
        return None

    monkeypatch.setattr(chain_mod, "model_call", fake_model_call)
    monkeypatch.setattr(chain, "_verify_stage", no_verify, raising=False)
    records = [{"procedures_performed": ["Biopsy Testis Incisional (Right)"], "procedures_ordered": [],
                "procedures_not_stated": ["surgical sperm extraction", "Orders: \u2022 FLU A B",
                                          "Biopsy Testis Incisional (Right)"]}]
    out = await chain._synthesize_records_attempt({}, records, 1)
    assert [d.official_diagnosis for d in out.diagnoses_mentioned] == ["Azoospermia"]
    assert [k for k in out.key_insights if k.startswith("Past procedures")] == [
        "Past procedures (status not stated): surgical sperm extraction"]


# ---- X8 ------------------------------------------------------------------------------------
def test_x8_med_name_and_date_post_checks(flags):
    flags(MEDICATION_NAME_CHECK_ENABLED=True, SUMMARY_DATE_CHECK_ENABLED=True)
    src = "Visit 12/02/2025\nTylenol or motrin prn\nFlu A Negative\nCollected 20251202171400+0000"
    r = AttachmentSummarizationResponse.model_construct(
        clinical_summary="Your visit was on December 2, 2025. You were seen again on December 9, 2025.",
        key_insights=["Flu test on 12/02/2025 was negative", "Seen on 12/09/2025", "No dates here"],
        medications_mentioned=["Tylenol as needed", "warfarin 5 mg nightly"], recommendations=[], instructions=[],
        follow_up=[], lab_results=[], procedures_mentioned=[], risk_factors=[], diagnoses_mentioned=[])
    _deterministic_post_checks(r, src, {"appointment_date": "2025-12-02"})
    assert r.medications_mentioned == ["Tylenol as needed"]
    assert r.key_insights == ["Flu test on 12/02/2025 was negative", "No dates here"]
    assert r.clinical_summary == "Your visit was on December 2, 2025."


def test_x8_appointment_date_allowed_and_flags_off_noop(flags):
    flags(MEDICATION_NAME_CHECK_ENABLED=False, SUMMARY_DATE_CHECK_ENABLED=False)
    r = AttachmentSummarizationResponse.model_construct(
        clinical_summary="Seen on March 24, 2021.", key_insights=[], medications_mentioned=["warfarin"],
        recommendations=[], instructions=[], follow_up=[], lab_results=[], procedures_mentioned=[], risk_factors=[])
    _deterministic_post_checks(r, "nothing", {"appointment_date": "2021-03-24"})
    assert r.medications_mentioned == ["warfarin"]
    flags(SUMMARY_DATE_CHECK_ENABLED=True)
    _deterministic_post_checks(r, "nothing", {"appointment_date": "2021-03-24"})
    assert r.clinical_summary == "Seen on March 24, 2021."


# ---- X9 ------------------------------------------------------------------------------------
def test_x9_evidence_fallback_keeps_only_verifiable():
    src = "Assessment\nHypertension, essential\nlosartan 25 MG tablet daily\nBP 134/83\n"
    s = _summary(diagnoses=["Hypertension, essential"], medications=["losartan 25 MG tablet daily", "warfarin 5 mg"],
                 evidence=["The patient has hypertension and takes losartan."])
    s.clinical_findings = ["BP 134/83", "Patient reports chest pain"]
    s.narrative_summary = "reworded narrative"
    assert _anchor_evidence_fallback(s, src) == ["Hypertension, essential"]
    assert s.clinical_findings == ["BP 134/83"]
    assert s.medications == ["losartan 25 MG tablet daily"] and s.narrative_summary == ""
    assert _anchor_evidence_fallback(_summary(diagnoses=["Fabricated disease"], evidence=["x"]), src) == []


@pytest.mark.asyncio
async def test_x9_fallback_fires_on_repair_only_with_flag(monkeypatch, flags):
    reworded = lambda: _summary(diagnoses=["Hypertension, essential"],
                                evidence=["The patient clearly has high blood pressure today."])
    flags(EVIDENCE_FALLBACK_ENABLED=True)
    chain, prompts = _chain(monkeypatch, [reworded(), reworded()])
    out = await chain._extract_batch([_doc(SOURCE)], 1, 1)
    assert len(prompts) == 2 and out[0].evidence_quotes == ["Hypertension, essential"]
    flags(EVIDENCE_FALLBACK_ENABLED=False)
    chain, _ = _chain(monkeypatch, [reworded(), reworded()])
    with pytest.raises(DocumentProcessingError) as info:
        await chain._extract_batch([_doc(SOURCE)], 1, 1)
    assert info.value.reason_code == "INVALID_SOURCE_EVIDENCE"


@pytest.mark.asyncio
async def test_x9_fallback_with_ungrounded_dx_still_fails(monkeypatch, flags):
    flags(EVIDENCE_FALLBACK_ENABLED=True, DROP_UNGROUNDED_DIAGNOSIS_ENABLED=False)
    bad = lambda: _summary(diagnoses=["Fabricated disease"], evidence=["reworded"])
    chain, _ = _chain(monkeypatch, [bad(), bad()])
    with pytest.raises(DocumentProcessingError):
        await chain._extract_batch([_doc(SOURCE)], 1, 1)


# ---- X10 -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_x10_invalid_output_splits_only_with_flag(monkeypatch, flags):
    text = "\n".join(f"Hypertension, essential {i} " + "y" * 40 for i in range(150))
    for on in (True, False):
        flags(EXTRACTION_INVALID_SPLIT_ENABLED=on)
        chain = AttachmentSummarizationChain.__new__(AttachmentSummarizationChain)
        calls = []

        async def attempt(batch, n, total, notes=None):
            calls.append(notes)
            if len(calls) == 1:
                raise DocumentProcessingError("MODEL_OUTPUT_INVALID")
            return [_summary(rid=batch[0].resource_id)]

        monkeypatch.setattr(chain, "_extract_batch_attempt", attempt, raising=False)
        out = await chain._extract_batch([_doc(text, rid="d:chunk:0")], 1, 1)
        assert (len(out), calls[1] is None) == ((2, True) if on else (1, False))
