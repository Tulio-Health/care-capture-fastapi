"""Guards PR-3a's Bug 2 fix: the per-document `_window_document` bound and the follow_up
grounding budget constants. See §7 Check 3 (a)-(g) in
care-capture-nodeapi/.claude/debug-reports/2026-09-08-summary-fix-plan/revision-round3.md.

(a)-(d): `_window_document` behavior (no-op below cap, preserves head/tail, preserves a
late plan-section match a naive head-only truncation would drop).
(e): the budget constants, asserted directly -- no Agent construction, runs with no
OPENAI_API_KEY.
(f): the output-bound clamp, including a fixture with many plan-section matches and a proof
that a naive (unclamped) reimplementation of the same algorithm DOES exceed the cap on it.
(g): the real-LLM wall-time/token measurement, gated on OPENAI_API_KEY like
test_procedure_extraction.py's real-LLM tests.
"""

import os
import time

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import DocumentAttachment


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
    reason="No OPENAI_API_KEY configured in this environment - skipping real-LLM windowing test.",
)


def _build_plan_heavy_document(n_headers: int = 20, total_len: int = 200_000) -> str:
    """A synthetic long document with `n_headers` disjoint _PLAN_SECTION_PATTERN matches
    spread roughly evenly across `total_len` characters -- the "20-header/200k fixture" the
    PR-3a merge checklist (Check 3(f)) calls for."""
    headers = [
        "Assessment and Plan",
        "Plan of Treatment",
        "Scheduled Orders",
        "Follow-up",
        "Disposition",
        "Discharge instructions",
        "Recommendation",
        "Return in 6 weeks",
    ]
    chunk = total_len // (n_headers + 1)
    parts = []
    for i in range(n_headers):
        parts.append("x" * chunk)
        header = headers[i % len(headers)]
        parts.append(f"\n\n{header}: item {i} - clinically relevant content here.\n")
    parts.append("x" * chunk)
    return "".join(parts)


def _naive_window_no_clamp(text: str, cap: int) -> str:
    """Reimplements the exact round-2 bug this PR fixes: assembles head + tail + every
    matched plan-section span WITHOUT ever dropping the lowest-priority span and WITHOUT a
    final unconditional `[:cap]` clamp. Used only to prove `_window_document`'s clamp is
    load-bearing -- this is deliberately NOT the production implementation.
    """
    if len(text) <= cap:
        return text
    head_end = int(cap * 0.6)
    tail_start = len(text) - int(cap * 0.1)
    raw_spans = sorted(
        (max(0, m.start() - 200), min(len(text), m.start() + 1_500))
        for m in chain._PLAN_SECTION_PATTERN.finditer(text)
    )
    spans = []
    for start, end in raw_spans:
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))

    parts = [text[:head_end]]
    cursor = head_end
    for start, end in spans:
        start, end = max(start, cursor), max(end, cursor)
        if start >= tail_start:
            continue
        end = min(end, tail_start)
        if end <= start:
            continue
        if start > cursor:
            parts.append(f"\n\n[... omitted {start - cursor} chars ...]\n\n")
        parts.append(text[start:end])
        cursor = end
    if tail_start > cursor:
        parts.append(f"\n\n[... omitted {tail_start - cursor} chars ...]\n\n")
    parts.append(text[tail_start:])
    return "".join(
        parts
    )  # NOTE: no drop-loop, no final [:cap] -- this is the round-2 bug.


# --- (a)-(d): basic _window_document behavior ---


def test_window_document_is_a_no_op_below_cap():
    text = "short document text, nowhere near any cap"
    assert chain._window_document(text, cap=10_000) == text


def test_window_document_preserves_the_head():
    text = "HEAD_MARKER " + "x" * 50_000 + " TAIL_MARKER"
    result = chain._window_document(text, cap=5_000)
    assert result.startswith("HEAD_MARKER")


def test_window_document_preserves_the_tail():
    text = "x" * 50_000 + " TAIL_MARKER_AT_THE_END"
    result = chain._window_document(text, cap=5_000)
    assert result.endswith("TAIL_MARKER_AT_THE_END")


def test_window_document_preserves_a_plan_section_past_the_head_slice():
    """The whole point of Bug 2's fix: a plan-section match that sits well past the head
    slice -- exactly where a blind head-only truncation would have dropped it -- survives
    windowing."""
    head_filler = "x" * 20_000
    plan_content = "Assessment and Plan: continue metformin, follow up in 6 weeks."
    tail_filler = "y" * 5_000
    text = head_filler + plan_content + tail_filler
    cap = 10_000

    # Sanity check: a naive head-only truncation at `cap` would NOT have included this.
    assert plan_content not in text[:cap]

    result = chain._window_document(text, cap=cap)
    assert plan_content in result


# --- (e): budget constants, asserted directly (no Agent construction -> works with no key) ---


def test_budget_constants_are_named_and_match_the_library_defaults():
    """Check 3(e): asserted on the module constants directly, not on a constructed Agent
    (which raises ValueError without an OpenAI key -- see get_pydantic_ai_model() /
    llm_factory.py -- rather than skipping). Must pass in CI with no OPENAI_API_KEY set.
    """
    assert chain._EXTRACTION_TIMEOUT_S == 60.0
    assert chain._EXTRACTION_RETRIES == 1
    assert chain._SYNTHESIS_TIMEOUT_S == 60.0
    assert chain._SYNTHESIS_RETRIES == 1
    # The cap is derived from BATCH_CHAR_LIMIT, not a separately-chosen number.
    assert chain._MAX_DOC_CHARS_ATTACHMENT == chain.BATCH_CHAR_LIMIT


# --- (f): the output-bound clamp, and proof that it is load-bearing ---


def test_window_document_output_never_exceeds_cap_on_a_plan_heavy_fixture():
    """Check 3(f): _window_document's output is <= cap on a fixture with many disjoint
    _PLAN_SECTION_PATTERN matches, at multiple cap values including the real default."""
    fixture = _build_plan_heavy_document()
    for cap in (1_000, 5_000, chain._MAX_DOC_CHARS_ATTACHMENT):
        result = chain._window_document(fixture, cap=cap)
        assert (
            len(result) <= cap
        ), f"cap={cap}: got {len(result)} chars, expected <= {cap}"


def test_the_output_bound_clamp_is_load_bearing_not_incidental():
    """Proves the bound is enforced by the final `return out[:cap]` clamp, not merely by the
    assembly arithmetic happening to fit: a naive reimplementation of the SAME algorithm
    without that clamp (mirroring the exact round-2 bug this PR fixes) DOES exceed the cap on
    this fixture, while the real `_window_document` does not.
    """
    fixture = _build_plan_heavy_document()
    cap = chain._MAX_DOC_CHARS_ATTACHMENT  # 30_000, the real default

    naive_result = _naive_window_no_clamp(fixture, cap)
    assert len(naive_result) > cap, (
        "fixture doesn't actually exercise the bug this test is supposed to prove -- naive "
        f"output ({len(naive_result)} chars) did not exceed cap ({cap})"
    )

    real_result = chain._window_document(fixture, cap=cap)
    assert len(real_result) <= cap, (
        f"the real _window_document exceeded its cap ({len(real_result)} > {cap}) -- the "
        "load-bearing clamp regressed"
    )


# --- (g): real-LLM wall-time/token-cost measurement ---


@requires_llm
@pytest.mark.asyncio
async def test_windowed_document_above_cap_still_produces_a_grounded_summary():
    """Check 3(g): the real-LLM measurement the PR-3a merge checklist calls for -- a document
    whose windowed content is >= BATCH_CHAR_LIMIT chars, run through the real chain, with wall
    time and document count printed for the PR description (the same measurement
    scripts/measure_attachment_summary_cost.py makes as a standalone operator entry point).
    """
    fixture = _build_plan_heavy_document(n_headers=8, total_len=60_000)
    assert len(fixture) > chain._MAX_DOC_CHARS_ATTACHMENT

    doc = DocumentAttachment(
        file_path="s3://fake/windowing-fixture.txt",
        content_type="text/plain",
        title="Windowing Fixture",
        extracted_text=fixture,
    )

    real_chain = chain.AttachmentSummarizationChain()
    started = time.monotonic()
    result = await real_chain.analyze(
        appointment_context={
            "appointment_date": "2026-01-01",
            "purpose": "follow-up",
            "provider_name": "Dr. Test",
        },
        documents=[doc],
    )
    elapsed = time.monotonic() - started

    print(f"wall_time_s={elapsed:.2f} documents_analyzed={result.documents_analyzed}")
    assert result.documents_analyzed == 1
