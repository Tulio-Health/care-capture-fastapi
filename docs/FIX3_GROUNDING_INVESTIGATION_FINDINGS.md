# Fix 3 — `CLINICAL_EVIDENCE_FAILED` investigation: findings and decision

Spec: `care-capture-nodeapi/.research/visit-summary-doc-filtering/round9-revision3.md`
Section 3.5 (`§3.5.0`–`§3.5.3`). Harness: `scripts/grounding_rerun.py`. Case list:
`scripts/grounding_rerun_cases.json`. Raw per-case captures (PHI, not committed):
`.qa_output/cases/*.json`.

**Decision: NO FIX.** Neither H1 (quote-matching normalization) nor H2 (issues strictness)
meets the pre-declared confirmation bar. No production code behavior changed. The two QA
observer hooks added to `clinical_grounding.py` and `procedure_extraction/chain.py` are
inert (`None`) unless a dev-only script explicitly registers them — see "What shipped" below.

## 1. Case resolution (§3.5.1)

Query: union of `error='CLINICAL_EVIDENCE_FAILED'` OR `reason='INVALID_SOURCE_EVIDENCE'` OR
`reason='DIAGNOSIS_WORDING_NOT_GROUNDED'` in `conversation_summaries.metadata->
'processing_errors'`, for `tulio-test46@yopmail.com` (dev).

**Result: 29 distinct appointments — matches the spec's predicted total exactly.** The
sub-breakdown does NOT match, which is itself a finding (the spec pre-declared this
possibility):

| Raw processing_error (error\|reason) | Spec predicted | Actual |
|---|---|---|
| `CLINICAL_EVIDENCE_FAILED` \| *(bare)* | 24 | 25 |
| `CLINICAL_EVIDENCE_FAILED` \| `INVALID_SOURCE_EVIDENCE` | 4 | 4 |
| `CLINICAL_EVIDENCE_FAILED` \| `DIAGNOSIS_WORDING_NOT_GROUNDED` | 1 | 1 |
| `CLINICAL_EVIDENCE_FAILED` \| `PROCEDURE_STATUS_NOT_GROUNDED` | *(not predicted)* | 1 |

Raw entries sum to 31, not 29, because 2 appointments carry two `CLINICAL_EVIDENCE_FAILED`-
class entries each; distinct-appointment count still lands on 29 by coincidence of that
overlap, not because the sub-breakdown matched. `PROCEDURE_STATUS_NOT_GROUNDED` existing at
all was not anticipated by the spec's narrative (though it IS in `document_extraction.py:47`'s
canonical group) — the spec's case-count story was written from an earlier/assumed state of
this data, not re-derived against it.

## 2. The central finding: the spec's mechanism attribution was wrong for most of the corpus

The spec assumed the 24–25 "bare" `CLINICAL_EVIDENCE_FAILED` rows were the LLM grounding
judge (`GROUNDING_VALIDATION_FAILED`, `clinical_grounding.py:435`). **Re-running the corpus
in-process with observer hooks on both `verify_grounding` and `_quote_supported` disproved
this for the large majority of cases**: those hooks fired zero times for most "bare" rows.

Tracing the gap led to a third raise site neither H1 nor H2 addresses:
`validate_single_subject` (`clinical_grounding.py:356`, now `:356-389` after instrumentation)
— a multi-patient-document-header safety guard, unrelated to quote-matching or judge
strictness, that raises the *same* canonical `CLINICAL_EVIDENCE_FAILED` code with no
distinguishing `reason` (because its `reason_code` equals its canonical `code`, and
`describe_error()` only persists `reason` when they differ). This is exactly the ambiguity
§3.5.1 pre-declared as unrecoverable from history — now measured, not assumed.

A second, smaller unaddressed mechanism also surfaced: `require_validated_summary`
(`validated_summary.py:18`), an in-process integrity-seal check, also bare
`CLINICAL_EVIDENCE_FAILED`/no reason, also outside H1/H2's scope.

**Full mechanism breakdown, all 29 cases (from captured events, not the ambiguous persisted
error/reason pair):**

| Mechanism | Count | In scope for H1/H2? |
|---|---|---|
| `validate_single_subject` (multi-patient header guard) | 20 | No — third, unaddressed mechanism |
| `verify_grounding` (the LLM judge) | 3 | H2 population |
| `_quote_supported`-gated (`validate_quotes` / diagnosis / procedure / evidence_quotes) | 4 | H1 population |
| `require_validated_summary` (integrity seal) | 2 | No — third, unaddressed mechanism |

This is the single most important output of this investigation: **69% of this corpus's
rejections are not grounding-judge or quote-matching failures at all.** Whether
`validate_single_subject`'s regex is itself over-triggering on these stress-test documents is
a legitimate follow-up question, but it is a *different*, un-hypothesized mechanism — fixing
it was never pre-declared in scope here, and doing so now would not be the evidence-first,
single-hypothesis-at-a-time process this task was scoped to. Recommended as a separate,
explicitly-scoped follow-up, not folded into this decision.

## 3. Harness validity (§3.5.1 gate)

- **29/29 cases (100%) reached a terminal verdict** — harness valid (≥90% required).
- **Verdict distribution: 29/29 rejected on re-run, 29/29 rejected historically** — identical,
  no material drift. (One case's *specific* reason changed between historical and re-run —
  `71bafa0d-...` was `PROCEDURE_STATUS_NOT_GROUNDED` historically, `GROUNDING_VALIDATION_FAILED`
  on re-run — consistent with expected LLM-sampling non-determinism across runs, not a harness
  defect; the case stayed rejected either way.)
- Fix 2 (the sanitize-and-revalidate parser fix) is already on this branch, so every re-run
  used production's current sanitized text — the same text the judge and quote-matcher see in
  production today (§3.5.3 point 4, the Fix 2/Fix 3 interaction guard — verified, not assumed).

## 4. H1 — quote-matching normalization: NOT CONFIRMED

Candidate: add Unicode NFKC normalization on top of the live whitespace-collapse + casefold
normalize, inside `_quote_supported`/`_normalize` (the correct site per §3.5.2's re-siting).

- **7 of 29 cases actually exercised `_quote_supported` with a real failure** (40 total
  `supported=False` events captured, frozen `(quote, source)` pairs, zero new LLM calls for
  this replay).
- **0 of 40 events flip to `True` under the candidate.** 4 of 40 have a normalized string that
  differs at all under NFKC (vs. the live normalize) — none of those 4 cross the 0.85
  threshold anyway (candidate score deltas were negligible).
- Score distribution: 34/40 events score < 0.5 (large divergence from any source span — not
  near-misses of any kind), 6/40 score in [0.5, 0.85) (closest: 0.836, on one case,
  `972e65f8-...`, where NFKC made zero textual difference). This is not formatting noise; the
  matcher is rejecting genuine content divergence, the pattern the pinned adversarial test
  suite (`test_quote_supported_fail_closed.py`) exists to catch.
- **Pre-declared bar: ≥5 of 29 flip reject→accept, with zero genuinely-ungrounded acceptances.
  Actual: 0 of 29 flip.** Decisively below threshold — the corpus's addressable population
  (7 cases) could not have reached 5 flips even at 100% success, and the real result was 0%.
- Regression guard: trivially passes (no flips to confirm, nothing to ship).

**No real-LLM confirmation re-run was needed** (§Step 3b in the harness exists for this, would
trigger automatically on any flip candidate) — the event-level replay result is unambiguous.

## 5. H2 — `issues` strictness: NOT CONFIRMED (premise does not occur in this corpus)

Candidate: severity-classify `issues`, fail only on grounding-class issues when
`supported=True`.

- **H2's addressable population is `supported=True AND issues non-empty` — the only shape of
  rejection that specific logic could possibly flip.**
- **All 3 real judge firings in this corpus had `supported=False`** (manually confirmed by
  reading the captured verdicts, not inferred): the judge explicitly said "not supported," a
  direct ungrounded-content judgment, not a strictness-on-stylistic-issues artifact.
- **0 of 29 cases have `supported=True` with non-empty issues.** H2's premise — minor/stylistic
  issues failing an otherwise-supported summary — never actually happened in this corpus.
  There is nothing to classify, let alone fix.

## 6. Decision (§3.5.3)

**NO FIX for either hypothesis.** The justified conclusion, per the pre-declared decision
rule: the safety gate is working correctly on the content it actually judges. The real lever
for this corpus's rejection rate is NOT the judge or the quote-matcher — it is
`validate_single_subject`'s multi-patient guard (69% of rejections), a mechanism outside this
investigation's two pre-declared hypotheses. Manufacturing a fix for H1 or H2 to have
"something to ship" would not be justified by this evidence and was explicitly ruled out by
the task's own pre-declared criteria.

**Regression guard:** N/A — no candidate fix shipped, so there is nothing that could regress a
previously-accepted summary.

## 7. What shipped

- `scripts/grounding_rerun.py` — the re-run harness (`--resolve-cases`, `--run`, `--report`,
  `--confirm-h1`).
- `scripts/grounding_rerun_cases.json` — the resolved 29-appointment-ID case list (no PHI:
  appointment IDs + non-PHI error/stage/reason metadata only). Committed per §3.5.1's
  reproducibility requirement.
- Two QA-observer hook points, both `None`/inert by default, both requiring explicit
  `register_qa_observer(...)` from the harness script to activate, gated by
  `scripts/grounding_rerun.py::require_qa_observer_enabled()` (requires `QA_OBSERVER=1` AND
  `Settings.APP_ENV != "production"` — the settings-object assertion is the real, env-var-proof
  gate):
  - `clinical_grounding.py`: `register_qa_observer` + hook calls in `verify_grounding`
    (event=`grounding_validation_failed`) and `validate_single_subject`
    (event=`multi_patient_subject`).
  - `procedure_extraction/chain.py`: `register_qa_observer` + a hook call inside
    `_quote_supported` covering every call site project-wide (also fixed, during testing, to
    fire on the exact-match/empty-quote fast paths it originally missed).
- `src/app/tests/unit/test_grounding_qa_observer.py` — 11 new tests: hooks are inert by
  default, hooks fire with correct payloads when registered, an observer exception never
  blocks the real raise, and (the mandatory coverage regardless of H1/H2 outcome) the
  prod-impossible gate — including the critical case: `QA_OBSERVER=1` set but
  `Settings.APP_ENV == "production"` still refuses.
- No changes to `_quote_supported`, `_normalize`, or the issues-strictness check themselves —
  neither hypothesis was confirmed, so neither candidate fix was implemented.

## 8. Test results

`uv run pytest src/app/tests/unit/`: **408 passed, 3 failed, 1 error** (10 skipped, 1 xfailed).
The 3 failures/1 error are `test_chat.py` (x3) and `test_health.py` (x1) — identical to the
documented pre-existing/unrelated baseline on this consolidated branch (397 passed, 3
failed/1 error). 408 = 397 baseline + 11 new tests added here, all passing.
