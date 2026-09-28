# Execution and release checklist

**Current state: all application cases NOT RUN, by user request.** Generating fixtures is not a baseline regression run. No pass rate or quality score is available yet.

## After fixes are implemented

1. Review cases and canonical error mappings with the implementation; keep stable case IDs. Complete the application adapter using real service code and mocked external boundaries.
2. Exercise the runner itself with explicit passing/failing/missing-field/missing-adapter checks before trusting its reports. No such tests have been run yet.
3. Run deterministic P0 cases first: MIME/encoding dispatch, parser exceptions, all-failed gate, procedure preservation, acquisition/batch accounting and safe unavailable/partial text.
4. Run remaining cases for cache freshness, translation, consolidation, chronology, resource limits, partial timeout and concurrency.
5. Inspect the adapter to confirm persistence is entirely in memory and no DB connection/DDL path exists. Save reports only under `qa/results/`. Fake repositories do not prove actual database locking; record this as an explicit limitation, not a passing claim.
6. Run opt-in real-model scan and clinical-grounding evaluation with predeclared thresholds and independent review. Record repetitions, model snapshot, prompt/parser versions, latency and cost.
7. Manually confirm the existing mobile summary display with synthetic unavailable, partial and failed-refresh payloads. No Node/mobile changes are required by this plan.
8. Treat BLOCKED, REVIEW_REQUIRED and ERROR as unresolved, not passes. Archive reviewed reports; do not turn off checks to obtain a green build.

## Coverage gaps that must remain visible

The supplied pack covers the named plan scenarios but is not a universal document corpus. Add fixtures before enabling these capabilities or making associated support claims:

- Genuine legacy binary DOC, encrypted DOCX, HEIC/HEIF, BMP and animated GIF conversion. The OLE header fixture is negative-only.
- Human-written handwriting samples with verified transcriptions. The unreadable image is artificially degraded printed text, not handwriting.
- Realistic multilingual scanned pages (Chinese text is currently native text), complex merged tables and unusual fonts with independently checked gold data.
- Vendor-specific attachment envelopes from each connector, appropriately synthetic or de-identified. Current connector examples are normalized scenarios only.
- Conflicting patient identities, multi-patient attachments and contradictory dated medication doses with an approved resolution policy.
- Network cancellation, retry-after headers, worker crashes and sustained memory/CPU/resource-load tests in a controlled environment.
- Full clinical image interpretation remains outside this document-reading feature; do not turn diagnostic images into scan-transcription positive cases.

Do not download production patient documents to fill these gaps. Use synthetic or separately approved de-identified data.

## Evaluation record template

Record per run: commit, environment, adapter version, enabled parser/converter/vision flags, model snapshot, prompt version, case IDs, attempts, outcome, evidence of rejection/preservation, reviewer and unresolved risks.

Before real-model evaluation, define numeric thresholds for transcription character/word error, critical clinical value/status/negation error, omitted facts, false acceptance of unreadable content, page completeness, latency and cost. The threshold choice requires qualified review; this pack does not fabricate an acceptable medical error rate.

Zero known critical unsupported claims on the regression set is a release requirement, not a guarantee that future summaries cannot hallucinate.

## Final resilience audit

Section 30 of the plan is authoritative for release readiness. Include `RES-*` cases and requirements R48–R54 for startup, overload, deadlines, lifecycle cleanup, source changes, metadata persistence and harness behavior. No release claim is justified while relevant cases are NOT RUN, BLOCKED or awaiting review. The no-database rule remains in force; actual DB locking/isolation is an explicitly unverified property.
