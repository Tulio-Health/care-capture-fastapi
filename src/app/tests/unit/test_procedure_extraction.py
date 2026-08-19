"""Unit tests for the procedure-extraction chain.

Validates the batch-shaped `ProcedureExtractionChain` against the 3 real sample procedure
reports (manually transcribed fixtures, matching samples/procedure-ground-truth.md in
care-capture-nodeapi) with a REAL LLM call — no mocking of the model itself, since the
whole point is to prove the extraction is factually accurate on real report text.

Requires a configured OPENAI_API_KEY (via SSM or env) — skipped otherwise, matching this
repo's settings-driven `get_pydantic_ai_model()` which raises without one.

Runs N=5 times (real, non-deterministic LLM calls) and asserts a pass-rate threshold
rather than 100%: see PASS_THRESHOLD below.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from src.app.chains.procedure_extraction.chain import (
    ProcedureExtractionChain,
    _quote_supported,
)
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummary,
)

N_RUNS = 5
# Real-LLM test: tolerate 1 flaky run out of 5 rather than demanding 100%, since a single
# transient omission/hallucination on a genuinely ambiguous phrasing is a model-quality signal
# to watch, not necessarily a regression. Tighten to 5/5 if this proves too lenient in practice.
PASS_THRESHOLD = 4

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
def long_cardiac_cath_document() -> DocumentAttachment:
    """Same cath-report shape as the `cardiac_cath` fixture, but padded with a plausible
    recovery-unit vitals flowsheet so the Recommendation/Disposition section starts past the
    OLD 20,000-char truncation point (verified in the fixture text itself) while staying well
    under the new `_MAX_DOC_CHARS` cap. Regression fixture for the deps/prompt truncation-
    mismatch bug."""
    return DocumentAttachment(
        file_path="s3://fake/samples/Sample-cardiac-cath-long.pdf",
        content_type="application/pdf",
        title="Cardiac Catheterization Report (Extended Recovery Flowsheet)",
        date=datetime(2026, 6, 29),
        document_type="Procedure Note",
        file_name="Sample-cardiac-cath-long.pdf",
        extracted_text=_load_fixture_text("cardiac_cath_long.txt"),
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


def _check_follow_up_grounding(
    label: str, summary: ProcedureSummary, source_text: str
) -> list[str]:
    """Checks the validator's guarantee directly on a single ProcedureSummary: real follow_up
    content must carry a quote-verified follow_up_source_quote, sentinel follow_up must have a
    null quote. Returns a list of human-readable failure descriptions (empty = all good).
    """
    issues = []
    if summary.follow_up == NOT_DOCUMENTED_FOLLOW_UP:
        if summary.follow_up_source_quote is not None:
            issues.append(
                f"{label}: follow_up is the sentinel but follow_up_source_quote is not null "
                f"({summary.follow_up_source_quote!r})"
            )
    else:
        if not summary.follow_up_source_quote:
            issues.append(
                f"{label}: follow_up is real content but follow_up_source_quote is empty"
            )
        elif not _quote_supported(summary.follow_up_source_quote, source_text):
            issues.append(
                f"{label}: follow_up_source_quote {summary.follow_up_source_quote!r} not found "
                "(verbatim/fuzzy) in the source document"
            )
    return issues


def _check_run(
    results: list[ProcedureSummary], procedure_documents: list[DocumentAttachment]
) -> list[str]:
    """Checks one extraction run against ground truth. Returns a list of failure descriptions
    (empty = the run fully passed)."""
    issues = []
    if len(results) != 3:
        return [f"expected 3 results, got {len(results)}"]

    cath, tee, surgery = results
    cath_src, tee_src, surgery_src = (doc.extracted_text for doc in procedure_documents)

    # --- Document 1: cardiac catheterization ---
    if not (
        "cath" in cath.procedure_type.lower()
        or "angioplasty" in cath.procedure_type.lower()
    ):
        issues.append(f"cath: unexpected procedure_type {cath.procedure_type!r}")
    if cath.procedure_date != "2026-06-29":
        issues.append(f"cath: unexpected procedure_date {cath.procedure_date!r}")
    if not any("ullah" in name.lower() for name in cath.performed_by):
        issues.append(f"cath: performed_by missing Ullah: {cath.performed_by!r}")
    # This report HAS an explicit recommendation/disposition section -> must NOT be the sentinel.
    if cath.follow_up == NOT_DOCUMENTED_FOLLOW_UP or not cath.follow_up:
        issues.append(
            f"cath: follow_up wrongly omitted (sentinel/empty): {cath.follow_up!r}"
        )
    issues.extend(_check_follow_up_grounding("cath", cath, cath_src))

    # --- Document 2: TEE ---
    if not (
        "tee" in tee.procedure_type.lower()
        or "echocardiogram" in tee.procedure_type.lower()
    ):
        issues.append(f"tee: unexpected procedure_type {tee.procedure_type!r}")
    if tee.procedure_date != "2026-07-06":
        issues.append(f"tee: unexpected procedure_date {tee.procedure_date!r}")
    if not any("strimel" in name.lower() for name in tee.performed_by):
        issues.append(f"tee: performed_by missing Strimel: {tee.performed_by!r}")
    # This report has NO follow-up/recommendation section -> must be exactly the sentinel.
    if tee.follow_up != NOT_DOCUMENTED_FOLLOW_UP:
        issues.append(f"tee: follow_up wrongly fabricated: {tee.follow_up!r}")
    issues.extend(_check_follow_up_grounding("tee", tee, tee_src))

    # --- Document 3: AVR surgery ---
    if not any(
        term in surgery.procedure_type.lower()
        for term in ["aortic valve", "avr", "surgery", "valve replacement"]
    ):
        issues.append(f"surgery: unexpected procedure_type {surgery.procedure_type!r}")
    if surgery.procedure_date != "2026-07-14":
        issues.append(f"surgery: unexpected procedure_date {surgery.procedure_date!r}")
    if not any("choi" in name.lower() for name in surgery.performed_by):
        issues.append(f"surgery: performed_by missing Choi: {surgery.performed_by!r}")
    # This report has NO follow-up/recommendation section -> must be exactly the sentinel.
    if surgery.follow_up != NOT_DOCUMENTED_FOLLOW_UP:
        issues.append(f"surgery: follow_up wrongly fabricated: {surgery.follow_up!r}")
    issues.extend(_check_follow_up_grounding("surgery", surgery, surgery_src))

    return issues


@requires_llm
async def test_procedure_extraction_against_ground_truth(procedure_documents):
    """Runs the real chain N_RUNS times against the 3 sample procedure reports and checks each
    run's output against manually-verified ground truth (see samples/procedure-ground-truth.md
    in care-capture-nodeapi) for type/date/performer, follow_up's critical documented-vs-not
    distinction, and the new quote-grounding guarantee (follow_up_source_quote must be present
    and verifiable whenever follow_up is real content, and null exactly when follow_up is the
    sentinel). Asserts an aggregate pass rate >= PASS_THRESHOLD/N_RUNS rather than requiring
    every single run to be perfect, since this is a real non-deterministic LLM call."""
    chain = ProcedureExtractionChain()

    passed = 0
    run_reports = []
    for run_idx in range(N_RUNS):
        results, failures = await chain.extract(procedure_documents)
        if failures:
            issues = [f"unexpected chain failures: {failures}"]
        else:
            issues = _check_run(results, procedure_documents)
        if not issues:
            passed += 1
        run_reports.append(
            f"run {run_idx + 1}: " + ("PASS" if not issues else "; ".join(issues))
        )

    report = "\n".join(run_reports)
    assert (
        passed >= PASS_THRESHOLD
    ), f"Only {passed}/{N_RUNS} runs passed (threshold: {PASS_THRESHOLD}/{N_RUNS}):\n{report}"


@requires_llm
async def test_procedure_extraction_follow_up_past_old_truncation_point(
    long_cardiac_cath_document,
):
    """Regression test for the deps/prompt truncation-mismatch bug: this fixture's
    Recommendation/Disposition section starts past the OLD 20,000-char truncation point but
    within the new `_MAX_DOC_CHARS` cap. Before the fix, the output_validator's `ctx.deps` held
    the FULL untruncated text while the prompt sent to the model was capped at 20,000 chars, so
    the validator would demand a follow_up the model was never shown for documents like this one
    -> an unwinnable ModelRetry loop that exhausted retries and silently dropped the document.
    Asserts the document is NOT dropped and follow_up is correctly extracted (non-sentinel,
    quote-grounded)."""
    source_text = long_cardiac_cath_document.extracted_text
    assert len(source_text) > 20_000, "fixture must exceed the old truncation point"
    assert (
        source_text.index("Recommendation:") > 20_000
    ), "fixture's follow-up section must start past the old truncation point"

    chain = ProcedureExtractionChain()
    summaries, failures = await chain.extract([long_cardiac_cath_document])

    assert not failures, f"document was wrongly dropped as a failure: {failures}"
    assert len(summaries) == 1, f"expected 1 result, got {len(summaries)}"

    summary = summaries[0]
    assert (
        summary.follow_up != NOT_DOCUMENTED_FOLLOW_UP
    ), f"follow_up was wrongly omitted (sentinel): {summary.follow_up!r}"
    issues = _check_follow_up_grounding("long_cardiac_cath", summary, source_text)
    assert not issues, "; ".join(issues)
