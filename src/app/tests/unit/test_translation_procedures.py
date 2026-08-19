"""Unit tests for the procedure-translation integrity fix.

Covers two layers:
1. Deterministic, no-LLM tests for `_merge_translated_procedures` (the whitelist-merge
   guard) and the `TranslatedSummary`/`TranslationResponse` model changes — these run in
   CI, no network, no mocking needed since the guard is a pure function.
2. Real-LLM `requires_llm` tests against the actual `TranslationChain`, mirroring
   `test_procedure_extraction.py`'s skip-gate structure — proves the prompt + guard
   combination behaves correctly against a real, non-deterministic model.

Requires a configured OPENAI_API_KEY (via SSM or env) for the `requires_llm` tests —
skipped otherwise.
"""

import os
from typing import Any, Dict, List
from uuid import uuid4

import pytest

from src.app.chains.translation.chain import TranslationChain
from src.app.models.translation import TranslatedSummary, TranslationResponse
from src.app.services.translation.translation_service import (
    _merge_translated_procedures,
)

N_RUNS = 5
# Real-LLM test: tolerate 1 flaky run out of 5 rather than demanding 100%, matching
# test_procedure_extraction.py's rationale — a single transient anchor/format drift is a
# model-quality signal to watch, not necessarily a regression.
PASS_THRESHOLD = 4


def _has_llm_credentials() -> bool:
    """Best-effort check for a usable OpenAI key without requiring SSM to be reachable."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    try:
        from src.app.core.settings import get_settings

        return bool(get_settings().OPENAI_API_KEY)
    except Exception:
        return False


requires_llm = pytest.mark.skipif(
    not _has_llm_credentials(),
    reason="No OPENAI_API_KEY configured in this environment - skipping real-LLM procedure translation test.",
)


# 3-procedure fixture shaped like ProcedureSummary.model_dump() output (see
# src/app/models/procedure_summarization.py) with distinct ISO dates, mirroring the fixture
# used in the closing-verification real-LLM pass.
PROCEDURE_FIXTURE: List[Dict[str, Any]] = [
    {
        "source_document_title": "Cardiac Catheterization Report",
        "procedure_type": "Cardiac catheterization with coronary angioplasty",
        "procedure_date": "2026-06-29",
        "performed_by": ["Ullah, MD (cardiologist)"],
        "reason": "You had chest pain and your doctor wanted to check the blood flow to your heart.",
        "procedure_details": "A thin tube was guided through a blood vessel to your heart to look at your coronary arteries.",
        "outcome": "A blockage was found and treated with a small balloon and stent.",
        "follow_up": "Take your prescribed blood thinner daily and follow up with cardiology in 2 weeks.",
        "follow_up_source_quote": "Follow up with cardiology in 2 weeks and continue aspirin 81mg daily.",
    },
    {
        "source_document_title": "Transesophageal Echocardiogram Report",
        "procedure_type": "Transesophageal echocardiogram (TEE)",
        "procedure_date": "2026-07-06",
        "performed_by": ["Strimel, MD (cardiologist)"],
        "reason": "Your doctor needed a closer look at your heart valves and chambers.",
        "procedure_details": "A small probe with an ultrasound camera was passed down your throat to take pictures of your heart.",
        "outcome": "Your heart valves and chambers appeared normal with no clots detected.",
        "follow_up": "Not documented in this procedure report.",
        "follow_up_source_quote": None,
    },
    {
        "source_document_title": "Operative Report - AVR",
        "procedure_type": "Aortic valve replacement (AVR) surgery",
        "procedure_date": "2026-07-14",
        "performed_by": ["Choi, MD (surgeon)"],
        "reason": "Your aortic valve was narrowed and needed to be replaced.",
        "procedure_details": "Your damaged aortic valve was removed and replaced with a new mechanical valve.",
        "outcome": "The new valve is functioning well with no complications during surgery.",
        "follow_up": "Not documented in this procedure report.",
        "follow_up_source_quote": None,
    },
]


# --- 1. Model round-trip + serialization (no LLM) ---


def test_translated_summary_round_trips_procedures() -> None:
    ts = TranslatedSummary(
        summary_text="hola",
        procedures=[{"reason": "translated reason", "procedure_date": "2026-06-29"}],
    )
    assert ts.procedures == [
        {"reason": "translated reason", "procedure_date": "2026-06-29"}
    ]

    ts_unset = TranslatedSummary(summary_text="hola")
    assert ts_unset.procedures is None


def test_translation_response_emits_procedures_key_including_when_none() -> None:
    """Pins the serialization property A4 (nodeapi) discriminates on: model_dump(by_alias=True)
    must always include the `procedures` key, even when it's None (no exclude_none anywhere
    in this path)."""
    kwargs = dict(
        id=uuid4(),
        appointment_id=uuid4(),
        user_id=uuid4(),
        summary_text="hola",
        key_points=None,
        medications=None,
        diagnoses=None,
        instructions=None,
        recommendations=None,
        translated_language="es",
        created_at="2026-01-15T10:30:00",
        updated_at="2026-01-15T10:30:00",
        created_by=uuid4(),
        updated_by=None,
    )

    resp_unset = TranslationResponse(**kwargs)
    dumped_unset = resp_unset.model_dump(by_alias=True)
    assert "procedures" in dumped_unset
    assert dumped_unset["procedures"] is None

    procedures = [{"reason": "translated reason", "procedure_date": "2026-06-29"}]
    resp_present = TranslationResponse(**{**kwargs, "procedures": procedures})
    dumped_present = resp_present.model_dump(by_alias=True)
    assert dumped_present["procedures"] == procedures


# --- 2. `_merge_translated_procedures` guard (no LLM, deterministic) ---


def test_merge_translated_procedures_passthrough_integrity() -> None:
    """Translated whitelist fields apply; every passthrough field stays byte-identical to the
    original even when the LLM output tries to alter/scramble it or omits a key entirely.
    """
    original = [dict(PROCEDURE_FIXTURE[0])]
    llm = [
        {
            "procedure_date": "2026-06-29",  # anchor unchanged
            "reason": "Tenia dolor en el pecho.",
            "procedure_details": "Insertamos un cateter.",
            "outcome": "No se encontraron bloqueos.",
            # follow_up intentionally omitted -> must be backfilled from original
            "performed_by": [
                "SCRAMBLED, NOT REAL"
            ],  # not in whitelist -> must be ignored
            "follow_up_source_quote": "a translated quote that must be ignored",
            "source_document_title": "A translated title that must be ignored",
            "procedure_type": "A translated type that must be ignored",
        }
    ]

    merged = _merge_translated_procedures(original, llm, uuid4())

    assert merged is not None
    assert len(merged) == 1
    m = merged[0]
    orig = original[0]

    # Whitelisted fields: translated values win.
    assert m["reason"] == "Tenia dolor en el pecho."
    assert m["procedure_details"] == "Insertamos un cateter."
    assert m["outcome"] == "No se encontraron bloqueos."
    # Missing whitelisted key backfilled from original.
    assert m["follow_up"] == orig["follow_up"]

    # Passthrough fields: byte-identical to original, NOT the LLM's altered values.
    assert m["performed_by"] == orig["performed_by"]
    assert m["follow_up_source_quote"] == orig["follow_up_source_quote"]
    assert m["source_document_title"] == orig["source_document_title"]
    assert m["procedure_type"] == orig["procedure_type"]
    assert m["procedure_date"] == orig["procedure_date"]


def test_merge_translated_procedures_count_mismatch_returns_none() -> None:
    original = [dict(PROCEDURE_FIXTURE[0]), dict(PROCEDURE_FIXTURE[1])]
    llm = [dict(PROCEDURE_FIXTURE[0])]
    assert _merge_translated_procedures(original, llm, uuid4()) is None


def test_merge_translated_procedures_reorder_rejected() -> None:
    """Elements 0 and 2 swapped (distinct procedure_date anchors) -> guard drops everything."""
    original = [dict(p) for p in PROCEDURE_FIXTURE]
    llm = [
        dict(PROCEDURE_FIXTURE[2]),
        dict(PROCEDURE_FIXTURE[1]),
        dict(PROCEDURE_FIXTURE[0]),
    ]
    assert _merge_translated_procedures(original, llm, uuid4()) is None


def test_merge_translated_procedures_llm_none_returns_none() -> None:
    original = [dict(PROCEDURE_FIXTURE[0])]
    assert _merge_translated_procedures(original, None, uuid4()) is None


# --- 3. Real-chain / guard pass-rate (requires_llm) ---


@requires_llm
async def test_translate_conversation_summary_procedures_real_llm() -> None:
    """Runs the real chain + real guard N_RUNS times with the 3-procedure fixture. Integrity
    of passthrough fields is structural now (see the no-LLM tests above) -- this test
    measures guard PASS-RATE: how often the procedure_date anchor survives a real
    translation round-trip, and that reason/procedure_details are actually translated.
    """
    chain = TranslationChain()
    summary_dict = {
        "summary_text": "Patient underwent a series of cardiac procedures over the summer.",
        "key_points": ["Cardiac catheterization performed", "Aortic valve replaced"],
        "medications": None,
        "diagnoses": ["Coronary artery disease", "Aortic stenosis"],
        "instructions": ["Take prescribed blood thinner daily"],
        "recommendations": None,
        "procedures": [dict(p) for p in PROCEDURE_FIXTURE],
    }

    passed = 0
    reports = []
    for run_idx in range(N_RUNS):
        merged = await chain.translate_conversation_summary(summary_dict, "es")
        guarded = _merge_translated_procedures(
            PROCEDURE_FIXTURE, merged.get("procedures"), uuid4()
        )

        issues = []
        if guarded is None:
            issues.append(
                "guard rejected (count mismatch or procedure_date anchor drift)"
            )
        else:
            for i, (orig, m) in enumerate(zip(PROCEDURE_FIXTURE, guarded)):
                if m["reason"] == orig["reason"]:
                    issues.append(f"[{i}] reason not translated")
                if m["procedure_details"] == orig["procedure_details"]:
                    issues.append(f"[{i}] procedure_details not translated")
                if m["performed_by"] != orig["performed_by"]:
                    issues.append(
                        f"[{i}] performed_by drifted (should be structurally impossible)"
                    )

        if not issues:
            passed += 1
        reports.append(
            f"run {run_idx + 1}: " + ("PASS" if not issues else "; ".join(issues))
        )

    report = "\n".join(reports)
    assert (
        passed >= PASS_THRESHOLD
    ), f"Only {passed}/{N_RUNS} runs passed (threshold: {PASS_THRESHOLD}/{N_RUNS}):\n{report}"


@requires_llm
async def test_translate_conversation_summary_no_procedures_stays_none() -> None:
    """Transcript-shaped summary (no `procedures` key) -> chain output `procedures` stays
    None; flat fields are still translated."""
    chain = TranslationChain()
    summary_dict = {
        "summary_text": "Patient reported feeling better after starting the new medication regimen.",
        "key_points": ["Feeling better", "New medication working well"],
        "medications": [{"name": "Lisinopril", "dosage": "10mg", "frequency": "daily"}],
        "diagnoses": ["Hypertension"],
        "instructions": ["Continue current medications"],
        "recommendations": [{"type": "Follow-up", "description": "Return in 3 months"}],
    }

    merged = await chain.translate_conversation_summary(summary_dict, "es")

    assert merged.get("procedures") is None
    assert merged["summary_text"] != summary_dict["summary_text"]
