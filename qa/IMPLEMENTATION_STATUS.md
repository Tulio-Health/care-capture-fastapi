# FastAPI implementation status

Updated: 2026-09-16. **Implementation candidate; not release-certified. Mock and selected live AI regressions have run. Persistence tests use in-memory boundaries; no database qualification has been performed.**

The full plan is not yet complete. The changes below are implemented in source; static checks do not establish runtime or clinical correctness.

## Implemented

- Shared, fail-closed extraction for attachment and procedure services. MIME case/parameters/aliases, explicit encodings and BOMs, signature detection, strict RTF parsing, XML entity rejection, HTML visible-text extraction, JSON/CSV parsing, bounded gzip, validated inline attachment base64, native PDF and DOCX extraction.
- No raw-document fallback. Unknown formats, corrupt data, encrypted files, unsafe containers and resource-limit violations become processing errors. Optional parser imports are local to their adapters.
- Killable parser/render subprocesses with time/CPU/memory limits; bounded S3 streaming and body cleanup; bounded download workers; per-worker admission, request deadlines and model-call budgets.
- Dedicated image/scanned-PDF OCR with transcription guardrails, schema validation, a separate image/transcription verification pass, and text validation before clinical model calls.
- Parsed-text integrity gate before attachment/procedure model calls. Attachment chunks account for the complete input; hierarchical synthesis replaces silent text windows. Source IDs are reconciled, evidence quotes checked, diagnosis wording retained, performed status checked, and clinical outputs independently verified before publication.
- Procedure extraction supports zero or multiple events. Consolidation only merges identical clinical content; it retains distinct facts. Failed/partial extraction cannot authorize pruning. Fully successful replacement can prune its own source rows.
- Existing `summaryText` and `summaryMetadata` carry unavailable/partial/no-document outcomes. Previously validated summaries are preserved with a visible, idempotent refresh-failure notice. Procedure failures do not create fictional procedure rows.
- Existing ORM mapping corrected for multiple summary sources. Publication uses PostgreSQL advisory locks, validates merged JSON and response shape before commit, and rejects older completed attempts when newer results already exist. No tables, columns or migrations were added.
- Appointment/patient ownership checks and authenticated-caller mapping; direct caregiver access is not inferred from a role. Trusted Node service credentials remain the delegation boundary.
- Inventory includes pending and malformed attachments; individual malformed metadata cannot reuse another document's path. Inventory errors are distinguished from an empty inventory.
- Completed concurrent sources survive sibling timeout. Cached objects use full response-model conversion. Attachment reuse requires current parsed-content and eligibility fingerprints, validated complete output, and a final source recheck. Transcript/FHIR cache reuse remains conservatively disabled.
- FHIR input retains complete structured records within an explicit budget, rejects embedded unparsed document envelopes, and parses narrative markup. Stored condition/medication displays retain status. Transcript input is ordered and bounded.
- Translation checks scalar types/numbers and clinical meaning. Health insights skip placeholders, retain coverage context, and detect updated summaries. Background insight generation is asynchronous and has a cross-worker publication lock.
- Import-safe application factory for injected QA lifespan/configuration; bounded startup checks and rule warm-up; unavailable mandatory dependencies prevent clinical work through readiness checks.
- Real parser/attachment-chain regression adapter for mock and live modes, with injected OpenAI clients and no database access. Added offline safety-gate tests. Unwired controls report BLOCKED rather than being ignored.

## Explicit limitations and remaining work

1. **Regression integration is partial.** `application_adapter.py` exercises real parsing/OCR/attachment chains. It does not yet implement every orchestration, persistence, authorization, cancellation, startup or fault-injection scenario in the 479-case catalog. Unsupported controls raise `NotImplementedError`; missing observations must not be represented as passes. Complete those integrations before treating the catalog as an executable release suite.
2. **Clinical oracle review is still required.** Mock outputs are boundary stubs, not clinical accuracy evidence. Live output and transcription must be assessed against independently authored source facts. A model verifier is not independent human approval or a guarantee against hallucination.
3. **Format coverage is deliberately bounded.** Legacy Office conversion, generic archives, macro/embedded-object documents, Word tracked changes, image-bearing Word/RTF/HTML containers, require additional approved adapters and currently fail closed. Optional bounded FHIR Binary/DocumentReference/Media transport and approved containers now have adapters behind disabled-by-default feature flags. Inline base64 within the connector attachment ingestion path is supported. Scanned PDFs and raster images use the dedicated OCR path.
4. **Operational qualification remains.** Validate IAM bucket/key scope and authorized connector storage layouts; deployment-wide capacity across replicas; source mutations during the final publication transaction; real database behavior for ambiguous commit acknowledgment recovery and isolation/locking; deployment shutdown/resource behavior; and the mobile rendering of each outcome. No DB-backed test has been run, and this pack must not connect to a DB.
5. **Resource limits are policies, not universal support.** Defaults include 50 MiB input, one million extracted characters, 300 native PDF pages, 20 OCR pages/frames, 100 attachments, 128 attachment chunks, 4 active summary jobs per worker and a 64-call job budget. Larger or unsupported inputs receive a contained outcome. Procedure/transcript/FHIR inputs still have explicit context ceilings; they do not have the attachment hierarchy.
6. **Public contract validation is partial.** In-memory HTTP response serialization tests passed; Response shapes remain the existing models. Metadata fields are additive. Confirm current Node/mobile behavior with synthetic outcomes before rollout; no Node or mobile code was changed.
7. **Review existing tests for updated contracts.** Internal `DocumentSummary` requires source identity/evidence; `ProcedureMention` requires a source quote; procedure extraction uses an event-list envelope; internal document inputs require the parsing seal. Do not weaken these gates to preserve stale mocks.

## Verification performed

- Python compile-only checks across application and QA source: passed after correcting an async FHIR integration error. These checks do not import or execute application code.
- Targeted Ruff undefined-name/syntax checks on changed implementation: passed.
- A repository-wide Ruff scan reports five pre-existing undefined-name findings in `ai_chat_intents/intend_identifier/chain.py` and `ai_chat_intents/upcoming_visit_intent/chain.py`, outside this change.
- Dependency lock updated for Pillow. Python 3.12 runtime dependencies installed in an isolated QA environment. The 53 offline safety tests passed after the content-independent grounding audit. Nine reporting tests passed, including separate safe-rejection and availability classification. Mock and live regressions have executed with explicit regression-only credentials; remaining failures, blocked cases and reviews prevent release qualification.

## Running regression

Use the project environment (`uv sync --frozen`) rather than the fixture-authoring environment. Use the commands in `qa/README.md`. Keep the regression key in `qa/.env.regression.local`; do not load application credentials.

The application now explicitly requests up to **4096 output tokens** per extraction/synthesis/OCR call. Set `REGRESSION_MAX_OUTPUT_TOKENS=4096` or higher in the local QA configuration before live execution. The existing local secret file was not opened or overwritten. The 20-call default intentionally limits spend and will not cover the full live profile; raise it deliberately for the chosen case set.

Results belong only in `qa/results/`. BLOCKED, REVIEW_REQUIRED and unexecuted cases are not passing tests. Do not deploy based only on static checks.

## Current report

Open `qa/results/report.html`; each execution overwrites it and its JSON companion. Every case links stored synthetic documents and complete observed output, with expected/actual assertion comparisons, human-review requirements and coverage health. The latest result supersedes historical timestamp reports. No database was connected to or written by these regressions.

## Synthetic data is not an application specification

Regression fixtures illustrate requirements; they do not define supported patient names, diagnoses, medications, laboratory tests, document identifiers, or exact model wording. Production logic must not recognize fixture filenames, case IDs or expected outputs. Canned outputs and fault injection belong only at test dependency boundaries. Prompt rules describe evidence and status requirements without copying the incident's clinical details.

The deterministic English claim checks are conservative supplementary checks, not a complete medical language parser. They can reject paraphrases and cannot prove that every unsupported assertion is detected. Semantic verification and independent clinical review remain necessary. Unsupported cases stay blocked or require review; expectations must not be weakened to obtain a passing report.

## Outcome reporting

A validation rejection is a safety success when the saved observations confirm that the unsafe candidate was withheld and only a nonclinical failure template with empty clinical fields reached the publication boundary. Such a valid-document case is labeled `SAFELY_REJECTED`, with summary generation separately recorded as `NOT_PRODUCED`. Original availability assertions remain available; no expected checks are changed. Deliberate rejection scenarios pass normally when their declared checks pass. Missing publication evidence and unrelated failed assertions cannot be reclassified as a safety success.
