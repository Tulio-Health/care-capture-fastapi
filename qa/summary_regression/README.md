# Summary parsing and AI regression pack

**Status: implementation and regression verification in progress.** Mock and selected live runs have executed. See `../results/report.html` for current results; no database operation is permitted.

This pack contains synthetic test documents, expected outcomes, fault-injection specifications and a mock/live/mixed runner for the [implementation plan](../summeryparsing%20and%20AI%20fix%20.md). It covers the Section 16 matrix, anomalies A01–A11, grounding/translation requirements and Section 26 vision extraction. It does not claim current application behavior passes.

All names, clinical statements, identifiers and records are fabricated. No real patient records or incident artifacts are included. Clinical facts are test assertions, not treatment advice.

## Contents

- [`../testdata/`](../testdata/): text, RTF, HTML, CDA XML, DOCX, PDF, scan images, safe small malformed/container inputs, gold transcriptions, canned model responses, prior persisted-state examples and connector/transcript data.
- `fixture_catalog.json`: MIME declarations, purposes, byte counts and SHA-256 hashes. File extensions are deliberately unreliable in some cases.
- `cases.json`: case IDs, plan references, inputs, configuration, injected failures and machine-readable assertions. Every case starts as `not_run`.
- `CASE_MATRIX.md`: readable inventory of cases.
- `COVERAGE.md` / `coverage.json`: plan requirements mapped to exact case IDs.
- `MIME_FORMAT_MATRIX.md`: format-wide MIME/parameter/alias and transport cases.
- `RTF_MIME_MATRIX.md`: focused RTF MIME aliases, parameters and encoding cases.
- `../results/`: one overwritten HTML/JSON report and stable per-case observed-output files; no reports are stored in a database.
- `ADAPTER_CONTRACT.md`: how to connect the fixed FastAPI code to these cases.
- `application_adapter.py`: default real parser/OCR/attachment-chain adapter for mock/live modes. Unsupported orchestration/fault controls remain BLOCKED.
- `adapter_template.py`: reference contract for additional integrations.
- `test_safety_gates.py`: offline safety checks for the production parsing boundary.
- `run_pack.py`: explicit mock/live/mixed runner using the same application adapter.
- `ai_runtime.py`: regression-specific configuration and budgeted sync/async OpenAI clients.
- `live_profile.json`: existing application case IDs eligible for live AI.
- `execution_context.py`: supplies mode and client factory to the adapter.
- `build_fixtures.py` / `build_cases.py`: regenerate assets/specifications only, without importing or running the application.
- `RELEASE_CHECKLIST.md`: execution sequence, manual checks and remaining fixture gaps.

## What the pack does and does not prove

There are three distinct levels:

1. **Synthetic assets and expectations:** supplied now. Document generation does not test the application.
2. **Mocked service regressions:** connect the actual fixed parser, orchestration, persistence and translation code through the adapter. Canned model responses exercise handling of failures/unsafe outputs; they do not measure actual model transcription accuracy.
3. **Real-model quality evaluation:** separately opted in, using the scan gold transcript and independently reviewed clinical facts. Record model/prompt versions, accuracy, omissions, latency and cost. A JSON schema match is not proof of medical fidelity.

No default adapter imports FastAPI, its settings or DB. `src/app/tests/conftest.py` currently includes database create/drop operations; this pack does not use it. Keep these tests separate until a safe isolated test harness is implemented. All persistence checks use fresh in-memory fake repositories. No production or test database connection, write, DDL or migration is permitted. Actual database transaction/locking behavior is outside this pack’s scope and must not be claimed as verified by mocks.

## Inspect now without executing regressions

Read `CASE_MATRIX.md` and `cases.json`. Optionally list case names only:

```sh
python3 qa/summary_regression/run_pack.py --list
```

The commands below are **for after implementation**. They have not been run:

```sh
# Implement the adapter first; the supplied template intentionally blocks.
python3 qa/summary_regression/run_pack.py --mode mock \
  --execute --adapter qa/summary_regression/adapter_template.py \
  --case PARSE-01 --case DATA-03

# Execute the wired deterministic suite later, with a real test adapter.
python3 qa/summary_regression/run_pack.py --mode mock \
  --execute --adapter /path/to/implemented_summary_adapter.py
```

Every executed run writes `qa/results/report.json` and `report.html`. The output location is fixed; no DB sink exists. Adapters must declare `PERSISTENCE_MODE="memory"` and use only in-memory fake repositories. This declaration is a contract check, not a sandbox for arbitrary Python; review adapter code before executing it.

The runner returns nonzero for failed, blocked, error or review-required cases. Missing observations fail checks. It never substitutes expected values for actual results. The runner and AI transport are newly authored and have not been exercised, respecting the request not to run regressions yet.

Live/mixed mode uses the same actual FastAPI adapter with regression-specific OpenAI clients. See [qa/README.md](../README.md) for `--mode`, `--env-file`, the ignored local key file and budgets. No standalone evaluation summarizer exists. The key is read only for an explicitly selected live execution or local configuration check. The actual application adapter still needs implementation after the fixes.

## Regenerating test data only

Committed fixtures are ready to use; consumers do not need authoring packages. To regenerate later in an isolated environment:

```sh
python3 -m venv /tmp/tulio-summary-fixtures
/tmp/tulio-summary-fixtures/bin/python -m pip install -r qa/summary_regression/requirements-fixtures.txt
/tmp/tulio-summary-fixtures/bin/python qa/summary_regression/build_fixtures.py
/tmp/tulio-summary-fixtures/bin/python qa/summary_regression/build_cases.py
python3 qa/summary_regression/build_coverage.py
```

These scripts write synthetic documents to `qa/testdata/` and specifications/catalogs to `qa/summary_regression/`. DOCX metadata and PDF encryption may introduce byte differences on regeneration; the catalog is rebuilt to match. Clinical source content and expected outcomes remain stable. Review fixture changes before accepting new hashes. Do not regenerate fixtures as part of ordinary regression execution.

## Important fixture details

- `long_middle_late.txt` places a diagnosis beyond 10,000 characters and a follow-up beyond 100,000 characters; assertions inspect model input coverage as well as output.
- `scanned.pdf` contains page images without an embedded text layer. `mixed.pdf` combines native and scanned pages; `mixed_region.pdf` has selectable footer text alongside a scanned clinical body.
- `scan_unreadable.png` is deliberately degraded. No model should reconstruct an assumed diagnosis from it.
- `encrypted.pdf` has the test-only password `qa-only-password`. Failure tests must not automatically supply it.
- `legacy_ole_header.doc` is intentionally truncated, not a genuine legacy Word document. It tests routing only; do not claim legacy DOC support from it.
- ZIP traversal and external-resource examples are inert test payloads. Test extraction in a temporary sandbox with network disabled. The expansion fixture is only 128 KiB uncompressed; configure low limits to test safeguards without producing a real decompression bomb.
- `connector_envelopes.json` describes normalized synthetic inputs, not authoritative Cerner/Fasten API schemas. Add sanitized vendor-specific examples before claiming connector conformance.
- `prior_state.json` is for in-memory fake repositories, not import into a production database.

Some cases intentionally assert normalized outcomes rather than exact prose. Manual review must assess table relationships, diagnosis retention and clinical meaning. The optional adapter projection is internal QA data and does not require public API, Node, mobile or DB changes.

Current implementation and remaining integrations are recorded in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md). The full 479-case suite is not yet wired.
