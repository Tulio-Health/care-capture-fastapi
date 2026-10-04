#!/usr/bin/env python3
"""Fix 3 (round9-revision3.md Sec 3.5.1) QA-observer re-run harness for the
CLINICAL_EVIDENCE_FAILED-class grounding judge.

Historical validation_issues/validation_candidate were NEVER persisted (deliberate
PHI-safety policy, clinical_grounding.py ~:435-441: "In-process diagnostics for synthetic
QA observers only"). The only way to get this evidence is to RE-RUN the cases through the
real production code path (AttachmentSummarizationService.analyze_attachments, same call
this branch's deployed API makes) and capture the in-process diagnostics via a QA observer
hook -- the already-sanctioned use of those attributes. This adds no new persistence, no
new log sink, and no production code path: the hook is `None` in every normal process,
including prod, and only this script's own process ever calls register_qa_observer.

Modelled on scripts/summary_report.py's CLI/settings-loading conventions (feat/summary-
report-tool branch) -- SAME SSM-settings-loading, SAME --batch/--appointment CLI shape,
SAME read-only-context style. Diverges deliberately on the call mechanism: summary_report.py
POSTs to the deployed HTTP API; this script calls the service IN-PROCESS, because the QA
observer hook must be live inside the same Python process that runs verify_grounding /
_quote_supported -- an HTTP call to a remote App Runner instance cannot attach a hook.

Usage:
    AWS_PROFILE=tuliodev AWS_DEFAULT_REGION=us-east-2 QA_OBSERVER=1 \
      uv run python scripts/grounding_rerun.py --resolve-cases

    AWS_PROFILE=tuliodev AWS_DEFAULT_REGION=us-east-2 QA_OBSERVER=1 \
      uv run python scripts/grounding_rerun.py --cases scripts/grounding_rerun_cases.json \
        --limit 6

    AWS_PROFILE=tuliodev AWS_DEFAULT_REGION=us-east-2 QA_OBSERVER=1 \
      uv run python scripts/grounding_rerun.py --cases scripts/grounding_rerun_cases.json \
        --report
"""

import argparse
import asyncio
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

STRESS_TEST_USER_EMAIL = "tulio-test46@yopmail.com"

CASES_FILE = Path(__file__).parent / "grounding_rerun_cases.json"
QA_OUTPUT_DIR = Path(__file__).parent.parent / ".qa_output"
CASE_RESULTS_DIR = QA_OUTPUT_DIR / "cases"  # one JSON per appointment_id, gitignored (PHI)


# --------------------------------------------------------------------------- config / safety


def load_config() -> None:
    """Populate DB_*/INTERNAL_SERVICE_KEY/OPENAI_API_KEY from SSM using the app's own loader.
    Verbatim pattern from scripts/summary_report.py (feat/summary-report-tool)."""
    from src.app.config.ssm_loader import load_ssm_configuration_sync

    load_ssm_configuration_sync()


def require_qa_observer_enabled() -> None:
    """Hard gate, impossible to satisfy in prod by construction.

    TWO independent conditions, both required:
      1. QA_OBSERVER=1 explicitly set -- an opt-in, not a default.
      2. The loaded Settings object itself (NOT the raw env var -- Settings.APP_ENV, read
         AFTER SSM loading) says APP_ENV != "production".

    (2) is the real gate. A stray QA_OBSERVER=1 set in a prod environment by mistake still
    refuses here, because Settings.APP_ENV in that environment reads "production" regardless
    of what QA_OBSERVER says -- there is no way to make this function return normally while
    pointed at a production configuration.
    """
    if os.environ.get("QA_OBSERVER") != "1":
        raise SystemExit(
            "Refusing to run: this script captures in-process clinical diagnostics for "
            "QA/offline review. Set QA_OBSERVER=1 explicitly to opt in."
        )
    from src.app.core.settings import get_settings

    settings = get_settings()
    if settings.APP_ENV == "production":
        raise SystemExit(
            f"Refusing to enable the QA observer: Settings.APP_ENV={settings.APP_ENV!r}. "
            "This script must never attach diagnostics capture in a production configuration, "
            "even if QA_OBSERVER=1 was set."
        )
    print(f"QA observer gate passed (Settings.APP_ENV={settings.APP_ENV!r}).")


def attach_observers(sink: "CaseSink") -> None:
    """Register the two QA observer hooks (clinical_grounding.py, procedure_extraction/
    chain.py) to append into the given case's event lists. Call require_qa_observer_enabled()
    BEFORE this -- this function does not re-check."""
    from src.app.services import clinical_grounding
    from src.app.chains.procedure_extraction import chain as procedure_chain

    def on_grounding_failed(*, event, source, payload, issues, supported) -> None:
        # event is "grounding_validation_failed" (the LLM judge, clinical_grounding.py:435)
        # or "multi_patient_subject" (validate_single_subject, clinical_grounding.py:356) --
        # same canonical CLINICAL_EVIDENCE_FAILED code, same absent `reason` field, but a
        # completely different mechanism neither H1 nor H2 addresses. Tagged so the report
        # does not conflate them (see --resolve-cases finding: 25 "bare" historical rows).
        sink.grounding_events.append(
            {
                "event": event,
                "source": source,
                "candidate": payload,
                "issues": issues,
                "supported": supported,
            }
        )

    def on_quote_checked(quote, source, supported, threshold) -> None:
        sink.quote_events.append(
            {
                "quote": quote,
                "source": source,
                "supported": supported,
                "threshold": threshold,
            }
        )

    clinical_grounding.register_qa_observer(on_grounding_failed)
    procedure_chain.register_qa_observer(on_quote_checked)


class CaseSink:
    """Per-case event buffer. The harness processes appointments strictly sequentially and
    re-registers a fresh sink before each one, so there is no cross-case contamination despite
    the observer hooks being module-level globals (asyncio is single-threaded; only one
    appointment's coroutine tree runs at a time)."""

    def __init__(self) -> None:
        self.grounding_events: list[dict] = []
        self.quote_events: list[dict] = []


# --------------------------------------------------------------------- step 1: case resolution


CASE_QUERY = """
select
    cs.appointment_id::text as appointment_id,
    jsonb_agg(pe) as processing_errors
from conversation_summaries cs,
     jsonb_array_elements(coalesce(cs.metadata::jsonb -> 'processing_errors', '[]'::jsonb)) pe
where cs.user_id = :user_id
  and (
    pe ->> 'error' = 'CLINICAL_EVIDENCE_FAILED'
    or pe ->> 'reason' = 'INVALID_SOURCE_EVIDENCE'
    or pe ->> 'reason' = 'DIAGNOSIS_WORDING_NOT_GROUNDED'
  )
group by cs.appointment_id
order by cs.appointment_id
"""


async def resolve_cases(user_email: str = STRESS_TEST_USER_EMAIL) -> dict:
    """Source of truth for the case set (Sec 3.5.1): the union, for the stress-test user, of
    error='CLINICAL_EVIDENCE_FAILED' OR reason='INVALID_SOURCE_EVIDENCE' OR
    reason='DIAGNOSIS_WORDING_NOT_GROUNDED' rows in conversation_summaries.metadata
    ->'processing_errors'. Emits the resolved appointment-ID list as the harness's FIRST
    artifact, with the raw per-appointment processing_errors entries, so any deviation from
    the spec's predicted 24+4+1=29 is visible rather than silently reconciled.
    """
    from sqlalchemy import select, text
    from src.app.db.config.database import get_session_factory
    from src.app.db.objects.entities.users import Users

    async with get_session_factory()() as db:
        user = (
            await db.execute(select(Users).where(Users.email == user_email))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"Stress-test user not found: {user_email}")
        rows = (
            await db.execute(text(CASE_QUERY), {"user_id": str(user.id)})
        ).all()

    cases = [
        {"appointment_id": r.appointment_id, "historical_processing_errors": r.processing_errors}
        for r in rows
    ]

    # Deviation accounting (Sec 3.5.1: "any deviation is itself a finding"). Tally raw
    # processing_error entries by (error, reason) across the WHOLE matched set, separately
    # from the per-appointment dedup above, so a sub-breakdown mismatch against the spec's
    # predicted 24/4/1 is visible even when the distinct-appointment total still lands on 29.
    tally: dict[str, int] = {}
    for case in cases:
        for pe in case["historical_processing_errors"]:
            key = f"{pe.get('error')}|{pe.get('reason', '')}"
            tally[key] = tally.get(key, 0) + 1

    result = {
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "user_email": user_email,
        "user_id": str(user.id),
        "expected_total": 29,
        "actual_distinct_appointments": len(cases),
        "raw_processing_error_tally": tally,
        "cases": cases,
    }
    return result


# --------------------------------------------------------------------------- step 2: re-run


async def rerun_case(db, appointment_id: str, user_id: str) -> dict:
    """Re-run ONE appointment through the real production entry point
    (AttachmentSummarizationService.analyze_attachments -- the same call this branch's
    deployed API makes), with force_regenerate=True so the cache can never short-circuit a
    fresh re-run, and the QA observer hooks attached so every grounding/quote-matching
    decision inside this call is captured to `sink`, in-process, instead of being discarded.
    """
    from src.app.models.attachment_summarization import AttachmentSummarizationRequest
    from src.app.services.summarization.attachment_summarization import (
        AttachmentSummarizationService,
    )

    sink = CaseSink()
    attach_observers(sink)
    request = AttachmentSummarizationRequest(
        appointment_id=appointment_id, user_id=user_id, force_regenerate=True
    )
    service = AttachmentSummarizationService(db)
    outcome: dict[str, Any] = {"appointment_id": appointment_id}
    try:
        summary = await service.analyze_attachments(request)
        meta = summary.metadata or {}
        errors = meta.get("processing_errors") or []
        terminal_error = errors[-1] if errors else None
        outcome.update(
            {
                "terminal": True,
                "verdict": "rejected" if terminal_error else "accepted",
                "error": (terminal_error or {}).get("error"),
                "reason": (terminal_error or {}).get("reason"),
                "processing_outcome": meta.get("processing_outcome"),
            }
        )
    except Exception as exc:  # the harness must not die on one bad case
        outcome.update(
            {
                "terminal": False,
                "verdict": "exception",
                "error": getattr(exc, "code", type(exc).__name__),
                "reason": getattr(exc, "reason_code", None),
                "exception_str": str(exc)[:500],
            }
        )
    finally:
        # Detach: do not let a stale sink leak into whatever runs next in this process.
        attach_observers(CaseSink())

    outcome["grounding_events"] = sink.grounding_events
    outcome["quote_events"] = sink.quote_events
    return outcome


async def run_harness(cases: list[dict], limit: Optional[int] = None, skip_existing: bool = False) -> list[dict]:
    require_qa_observer_enabled()
    from src.app.db.config.database import get_session_factory
    from sqlalchemy import select
    from src.app.db.objects.entities.users import Users

    targets = cases if limit is None else cases[:limit]
    if skip_existing:
        targets = [c for c in targets if not (CASE_RESULTS_DIR / f"{c['appointment_id']}.json").exists()]
    CASE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    async with get_session_factory()() as db:
        user = (
            await db.execute(select(Users).where(Users.email == STRESS_TEST_USER_EMAIL))
        ).scalar_one_or_none()
        for i, case in enumerate(targets, 1):
            appt = case["appointment_id"]
            print(f"[{i}/{len(targets)}] {appt} re-running...")
            result = await rerun_case(db, appt, str(user.id))
            result["historical_processing_errors"] = case.get("historical_processing_errors")
            out_path = CASE_RESULTS_DIR / f"{appt}.json"
            out_path.write_text(json.dumps(result, indent=2, default=str))
            print(
                f"[{i}/{len(targets)}] {appt} verdict={result['verdict']} "
                f"error={result.get('error')} reason={result.get('reason')} "
                f"grounding_events={len(result['grounding_events'])} "
                f"quote_events={len(result['quote_events'])} -> {out_path}"
            )
            results.append(result)
    return results


# ------------------------------------------------------------------ step 3: candidate H1/H2


def _normalize_candidate_h1(s: str) -> str:
    """H1 candidate: adds Unicode NFKC normalization on top of the live `_normalize`
    (whitespace collapse + casefold). NFKC folds compatibility variants that the live
    whitespace/case normalization does not touch -- curly quotes/apostrophes, non-breaking
    spaces, full-width punctuation, ligatures -- any of which defeats BOTH the substring
    check and the difflib fuzzy score if the source and the model's quoted text disagree on
    them even though they are the same clinical content.
    """
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def _quote_supported_candidate_h1(quote: str, source: str, threshold: float = 0.85) -> bool:
    import difflib

    q, src = _normalize_candidate_h1(quote), _normalize_candidate_h1(source)
    if not q:
        return False
    if q in src:
        return True
    matcher = difflib.SequenceMatcher(None, q, src)
    match = matcher.find_longest_match(0, len(q), 0, len(src))
    return match.size / max(len(q), 1) >= threshold


def classify_case(r: dict) -> str:
    """Which mechanism actually produced this case's terminal verdict, using the captured
    events rather than the ambiguous persisted (error, reason) pair -- validate_single_subject
    and the LLM judge both persist as bare error='CLINICAL_EVIDENCE_FAILED', reason=None
    (Sec 3.5.1's whole premise: this distinction is unrecoverable from history alone)."""
    if r["verdict"] == "accepted":
        return "accepted"
    if r["verdict"] == "exception":
        return "harness_exception"
    ge_events = r.get("grounding_events") or []
    if any(e.get("event") == "multi_patient_subject" for e in ge_events):
        return "multi_patient_subject"  # out of scope for H1 and H2
    if any(e.get("event") == "grounding_validation_failed" for e in ge_events):
        return "judge_rejected"  # H2 population
    if r.get("quote_events"):
        return "quote_gated"  # H1 population (INVALID_SOURCE_EVIDENCE / DIAGNOSIS_WORDING_NOT_GROUNDED / PROCEDURE_STATUS_NOT_GROUNDED)
    return "other_unobserved"  # rejected for a reason neither hook covers (e.g. upstream extraction/parsing failure)


def replay_h1(all_results: list[dict]) -> dict:
    """Deterministic, zero-LLM-call replay: recompute every captured quote-matching event
    under the H1 candidate normalize, using the FROZEN (quote, source) pairs the live run
    already captured -- no new model call, so this cannot itself introduce non-determinism.

    ELIGIBILITY (fixed after the first real run surfaced a bug in an earlier draft of this
    function: checking `r["error"]` against the three quote-gated reason codes never
    matched anything, because `.error` is always the CANONICAL code "CLINICAL_EVIDENCE_FAILED" --
    document_extraction.py's _ERROR_CODE_GROUPS collapses INVALID_SOURCE_EVIDENCE /
    DIAGNOSIS_WORDING_NOT_GROUNDED / PROCEDURE_STATUS_NOT_GROUNDED / GROUNDING_VALIDATION_
    FAILED into it; the specific one only ever survives on `.reason`, and even that is not
    always populated -- see classify_case's docstring. Eligibility is therefore keyed off
    the captured events themselves, not the persisted code: a case is ELIGIBLE when it has
    at least one quote_event with supported=False (i.e. _quote_supported's matching was
    actually exercised and actually failed at least once for this case).

    A case is a CANDIDATE FLIP when ALL of its supported=False events become True under the
    candidate (matching the real control flow -- every call site fails the whole check if
    ANY one quote does not match, e.g. validate_quotes' `any(...)`, or the evidence_quotes-
    empty-after-drop check) AND no supported=True event becomes False (the per-case half of
    the regression guard; the global half -- zero previously-ACCEPTED cases regressing -- is
    checked separately in replay_regression_guard).

    This flags candidates for REAL re-run confirmation (rerun_with_candidate_h1) -- it does
    not itself count as proof, because repair-retry control flow in chain.py (one retry on
    CLINICAL_EVIDENCE_FAILED) is not reproduced here.
    """
    flips, regressions, per_case = [], [], []
    for r in all_results:
        events = r.get("quote_events") or []
        false_events = [e for e in events if not e["supported"]]
        if not false_events:
            continue
        all_false_flip_true, any_true_flips_false = True, False
        for e in events:
            cand = _quote_supported_candidate_h1(e["quote"], e["source"], e["threshold"])
            if not e["supported"] and not cand:
                all_false_flip_true = False
            if e["supported"] and not cand:
                any_true_flips_false = True
        case_entry = {
            "appointment_id": r["appointment_id"],
            "error": r.get("error"),
            "reason": r.get("reason"),
            "n_false_events": len(false_events),
            "all_false_events_flip_true": all_false_flip_true,
            "any_true_event_regresses": any_true_flips_false,
            "candidate_flip": bool(
                r["verdict"] == "rejected" and all_false_flip_true and not any_true_flips_false
            ),
        }
        per_case.append(case_entry)
        if any_true_flips_false:
            regressions.append(r["appointment_id"])
        if case_entry["candidate_flip"]:
            flips.append(r["appointment_id"])
    return {"flip_candidates": flips, "event_level_regressions": regressions, "per_case": per_case}


def replay_h2(all_results: list[dict]) -> dict:
    """H2 evidence base: every captured grounding_event where supported=True but issues is
    non-empty -- the ONLY population H2 (severity-classify issues) could possibly flip, since
    a case where the judge said supported=False fails regardless of issues content. This
    function does not auto-classify; it surfaces the raw issue strings for the pre-declared
    manual read (Sec 3.5.1's confirmation criteria require a human read of every flip, not a
    heuristic)."""
    candidates = []
    for r in all_results:
        for ev in r.get("grounding_events") or []:
            if ev.get("supported") is True and ev.get("issues"):
                candidates.append(
                    {
                        "appointment_id": r["appointment_id"],
                        "issues": ev["issues"],
                        "candidate_payload_keys": sorted(ev["candidate"])
                        if isinstance(ev["candidate"], dict)
                        else None,
                    }
                )
    return {"h2_candidate_cases": candidates}


# ------------------------------------------------------------- step 3b: real confirmation run


async def rerun_with_candidate_h1(db, appointment_id: str, user_id: str) -> dict:
    """Real confirmation pass for ONE flip candidate: monkeypatches
    procedure_extraction.chain._quote_supported to the H1 candidate for the duration of this
    one call, then re-runs the full production chain for real (repair-retry control flow
    included) to get a true terminal verdict -- not an approximation. Restores the live
    function in a finally block regardless of outcome."""
    from src.app.chains.procedure_extraction import chain as procedure_chain

    live_fn = procedure_chain._quote_supported
    procedure_chain._quote_supported = _quote_supported_candidate_h1
    # clinical_grounding.validate_quotes and attachment_summarization.chain both imported
    # `_quote_supported` as a bare name reference resolved at CALL time via module attribute
    # lookup (clinical_grounding does `from ... import _quote_supported` INSIDE the function
    # body, attachment_summarization/chain.py imports it at module scope as `_quote_supported`
    # -- patch that module's binding too, or the module-scope import keeps the live function).
    from src.app.chains.attachment_summarization import chain as attachment_chain

    live_module_ref = attachment_chain._quote_supported
    attachment_chain._quote_supported = _quote_supported_candidate_h1
    try:
        return await rerun_case(db, appointment_id, user_id)
    finally:
        procedure_chain._quote_supported = live_fn
        attachment_chain._quote_supported = live_module_ref


# --------------------------------------------------------------------------- step 4: guard


def replay_regression_guard(all_results: list[dict], h1_flip_ids: set[str]) -> dict:
    """Hard gate (Sec 3.5.1): zero previously-ACCEPTED summaries may become rejected under
    any candidate. Checks every quote_event captured on an ACCEPTED case (verdict=='accepted')
    -- if any of those flips from supported=True (live) to False under the H1 candidate, that
    is a regression and VETOES shipping H1 regardless of flip count elsewhere."""
    violations = []
    for r in all_results:
        if r["verdict"] != "accepted":
            continue
        for e in r.get("quote_events") or []:
            if e["supported"] and not _quote_supported_candidate_h1(
                e["quote"], e["source"], e["threshold"]
            ):
                violations.append(r["appointment_id"])
                break
    return {"regression_guard_violations": violations, "passes": not violations}


# --------------------------------------------------------------------------------- CLI


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resolve-cases", action="store_true", help="Resolve the case set and write it to --cases-out.")
    p.add_argument("--cases-out", default=str(CASES_FILE))
    p.add_argument("--cases", default=str(CASES_FILE), help="Case list JSON to read for --run/--report.")
    p.add_argument("--run", action="store_true", help="Re-run cases through the production chain with QA observers attached.")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--skip-existing", action="store_true", help="Skip appointment_ids that already have a result in .qa_output/cases/ (resume a chunked run).")
    p.add_argument("--report", action="store_true", help="Summarize already-captured .qa_output/cases/*.json: validity, H1/H2 evidence.")
    p.add_argument("--confirm-h1", action="store_true", help="Real re-run of H1 flip candidates with the candidate normalize, for terminal-verdict confirmation.")
    return p.parse_args()


async def _main() -> None:
    args = parse_args()
    load_config()

    if args.resolve_cases:
        result = await resolve_cases()
        Path(args.cases_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"Resolved {result['actual_distinct_appointments']} appointments (expected {result['expected_total']}).")
        print(json.dumps(result["raw_processing_error_tally"], indent=2))
        print(f"-> {args.cases_out}")
        return

    cases_payload = json.loads(Path(args.cases).read_text())
    cases = cases_payload["cases"]

    if args.run:
        await run_harness(cases, limit=args.limit, skip_existing=args.skip_existing)
        return

    if args.confirm_h1:
        require_qa_observer_enabled()
        all_results = [json.loads(p.read_text()) for p in sorted(CASE_RESULTS_DIR.glob("*.json"))]
        h1 = replay_h1(all_results)
        from src.app.db.config.database import get_session_factory
        from sqlalchemy import select
        from src.app.db.objects.entities.users import Users

        async with get_session_factory()() as db:
            user = (await db.execute(select(Users).where(Users.email == STRESS_TEST_USER_EMAIL))).scalar_one_or_none()
            confirmed = []
            for appt in h1["flip_candidates"]:
                print(f"confirming H1 flip candidate {appt}...")
                result = await rerun_with_candidate_h1(db, appt, str(user.id))
                confirmed.append(result)
                out = QA_OUTPUT_DIR / "h1_confirm" / f"{appt}.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, indent=2, default=str))
                print(f"  -> verdict={result['verdict']} error={result.get('error')} -> {out}")
        return

    if args.report:
        all_results = [json.loads(p.read_text()) for p in sorted(CASE_RESULTS_DIR.glob("*.json"))]
        total = len(cases)
        terminal = sum(1 for r in all_results if r["terminal"])
        print(f"Harness coverage: {len(all_results)}/{total} cases have a result on disk.")
        print(f"Terminal verdicts: {terminal}/{total} ({terminal / total:.0%})." if total else "no cases")
        print(f"Harness valid (>=90% terminal, Sec 3.5.1): {terminal / total >= 0.90 if total else False}")
        by_verdict: dict[str, int] = {}
        for r in all_results:
            by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
        print("Verdict distribution:", json.dumps(by_verdict, indent=2))

        by_mechanism: dict[str, int] = {}
        for r in all_results:
            m = classify_case(r)
            by_mechanism[m] = by_mechanism.get(m, 0) + 1
        print("Mechanism breakdown (from captured events, not the persisted error/reason pair):")
        print(json.dumps(by_mechanism, indent=2))

        h1 = replay_h1(all_results)
        print(f"\nH1-eligible cases (>=1 supported=False quote_event): {len(h1['per_case'])}")
        print(json.dumps(h1["per_case"], indent=2))
        print(f"H1 candidate flips (pre-confirmation, event-level replay): {len(h1['flip_candidates'])}")
        print(json.dumps(h1["flip_candidates"], indent=2))
        if h1["event_level_regressions"]:
            print("H1 event-level regressions (would veto):", h1["event_level_regressions"])
        guard = replay_regression_guard(all_results, set(h1["flip_candidates"]))
        print(f"Regression guard passes: {guard['passes']}")
        if not guard["passes"]:
            print("VIOLATIONS:", guard["regression_guard_violations"])

        h2 = replay_h2(all_results)
        print(f"\nH2 candidate cases (supported=True, issues non-empty): {len(h2['h2_candidate_cases'])}")
        for c in h2["h2_candidate_cases"]:
            print(f"  {c['appointment_id']}: {c['issues']}")
        return

    print("Nothing to do -- pass --resolve-cases, --run, --confirm-h1, or --report.")


if __name__ == "__main__":
    asyncio.run(_main())
