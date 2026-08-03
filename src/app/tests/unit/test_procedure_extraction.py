"""Unit tests for the procedure-extraction chain.

Validates the batch-shaped `ProcedureExtractionChain` against the 3 real sample procedure
reports (manually transcribed fixtures, matching samples/procedure-ground-truth.md in
care-capture-nodeapi) with a REAL LLM call — no mocking of the model itself, since the
whole point is to prove the extraction is factually accurate on real report text.

Requires a configured OPENAI_API_KEY (via SSM or env) — skipped otherwise, matching this
repo's settings-driven `get_pydantic_ai_model()` which raises without one.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from src.app.chains.procedure_extraction.chain import ProcedureExtractionChain
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.procedure_summarization import NOT_DOCUMENTED_FOLLOW_UP

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "procedure_reports"


def _load_fixture_text(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text()


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
    reason="No OPENAI_API_KEY configured in this environment - skipping real-LLM procedure extraction test.",
)


@pytest.fixture
def procedure_documents() -> list[DocumentAttachment]:
    return [
        DocumentAttachment(
            file_path="s3://fake/samples/Sample-cardiac-cath.pdf",
            content_type="application/pdf",
            title="Cardiac Catheterization Report",
            date=datetime(2026, 6, 29),
            document_type="Procedure Note",
            file_name="Sample-cardiac-cath.pdf",
            extracted_text=_load_fixture_text("cardiac_cath.txt"),
        ),
        DocumentAttachment(
            file_path="s3://fake/samples/Sample-TEE.pdf",
            content_type="application/pdf",
            title="Transesophageal Echocardiogram Report",
            date=datetime(2026, 7, 6),
            document_type="Procedure Note",
            file_name="Sample-TEE.pdf",
            extracted_text=_load_fixture_text("tee.txt"),
        ),
        DocumentAttachment(
            file_path="s3://fake/samples/Sample-Heart-surgery.pdf",
            content_type="application/pdf",
            title="Operative Report - AVR",
            date=datetime(2026, 7, 14),
            document_type="Operative Note",
            file_name="Sample-Heart-surgery.pdf",
            extracted_text=_load_fixture_text("heart_surgery.txt"),
        ),
    ]


@requires_llm
async def test_procedure_extraction_against_ground_truth(procedure_documents):
    """Runs the real chain against the 3 sample procedure reports and checks the output
    against manually-verified ground truth (see samples/procedure-ground-truth.md in
    care-capture-nodeapi) for type/date/performer, and checks follow_up's critical
    documented-vs-not-documented distinction exactly."""
    chain = ProcedureExtractionChain()
    results = await chain.extract(procedure_documents)

    assert len(results) == 3

    cath, tee, surgery = results

    # --- Document 1: cardiac catheterization ---
    assert "cath" in cath.procedure_type.lower() or "angioplasty" in cath.procedure_type.lower()
    assert cath.procedure_date == "2026-06-29"
    assert any("ullah" in name.lower() for name in cath.performed_by)
    # This report HAS an explicit recommendation/disposition section -> must NOT be the sentinel.
    assert cath.follow_up != NOT_DOCUMENTED_FOLLOW_UP
    assert len(cath.follow_up) > 0

    # --- Document 2: TEE ---
    assert "tee" in tee.procedure_type.lower() or "echocardiogram" in tee.procedure_type.lower()
    assert tee.procedure_date == "2026-07-06"
    assert any("strimel" in name.lower() for name in tee.performed_by)
    # This report has NO follow-up/recommendation section -> must be exactly the sentinel.
    assert tee.follow_up == NOT_DOCUMENTED_FOLLOW_UP

    # --- Document 3: AVR surgery ---
    assert any(
        term in surgery.procedure_type.lower() for term in ["aortic valve", "avr", "surgery", "valve replacement"]
    )
    assert surgery.procedure_date == "2026-07-14"
    assert any("choi" in name.lower() for name in surgery.performed_by)
    # This report has NO follow-up/recommendation section -> must be exactly the sentinel.
    assert surgery.follow_up == NOT_DOCUMENTED_FOLLOW_UP
