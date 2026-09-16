# FastAPI summary regression QA

**Workflow: implement the FastAPI fixes, wire the test adapter, then run regressions against that fixed FastAPI code.** Both mocked and live-AI tests exercise the same application parsers, chains, prompts, validators, orchestration and persistence decisions. There is no separate replacement summarizer.

**Mock and selected live regressions have run; see the current report for results.** The pack contains 494 case specifications, 114 synthetic fixtures and 54 requirement groups. The default `application_adapter.py` now exercises the real FastAPI parser/OCR/attachment chain in mock and live modes. The formerly blocked orchestration/fault cases are integrated; missing external prerequisites still report BLOCKED. These counts are specifications, not passing tests. See [implementation status and remaining work](IMPLEMENTATION_STATUS.md).

## Contents

| Resource | Purpose |
|---|---|
| [Implementation status](IMPLEMENTATION_STATUS.md) | Implemented changes, limits and remaining release work |
| [Fix plan](<summeryparsing and AI fix .md>) | Approved FastAPI implementation plan |
| [Pack guide](summary_regression/README.md) | Fixtures and boundaries |
| [Case matrix](summary_regression/CASE_MATRIX.md) | All case IDs |
| [Coverage map](summary_regression/COVERAGE.md) | Plan requirements and explicit limitations |
| [MIME matrix](summary_regression/MIME_FORMAT_MATRIX.md) | All-format MIME/parameter coverage |
| [RTF matrix](summary_regression/RTF_MIME_MATRIX.md) | Additional RTF cases |
| [Adapter contract](summary_regression/ADAPTER_CONTRACT.md) | Connecting the real fixed FastAPI pipeline |
| [Live profile](summary_regression/live_profile.json) | Selected existing cases to repeat using real OpenAI |
| [Environment example](.env.regression.example) | Regression-only configuration without secrets |
| [Results](results/) | Local reports; never database rows |

## Mock, live and mixed modes

| Mode | FastAPI implementation | AI boundary | Other external dependencies |
|---|---|---|---|
| `mock` | Actual fixed code | Canned responses/errors to test deterministic behavior | Local files and in-memory fakes |
| `live` | Same actual fixed code | Real OpenAI through injected regression clients | Same local files and in-memory fakes |
| `mixed` | Same actual fixed code | Full mocked selection plus live-profile cases | Same local files and in-memory fakes |

Fault cases remain mocked: real AI cannot reliably produce a specific timeout, malformed response or fabricated claim on demand. Live cases compare actual application output to expected source facts, including diagnoses, statuses, numbers, units and scan coverage. Gold transcriptions are evaluation oracles; they must never be supplied as fake vision outputs in live mode. The runner removes the canned `vision_response` setting for live cases.

Live runs also require recorded human review of actual summaries. Passing machine assertions without review yields `REVIEW_REQUIRED`, not a claim of clinical correctness. The model cannot approve its own output. Repeat critical live cases using `--repeat` to expose variability.

The initial live profile is intentionally a subset of the 494 cases. Add a case only after its adapter path is wired to actual FastAPI code and its accuracy oracle is appropriate for real AI. Optional converters and incomplete fixes remain BLOCKED.

## Regression-specific OpenAI key

Keep the key separate from the application's `.env`:

```text
care-capture-fastapi/
  .env                         # application settings; regression does not load this
  qa/
    .env.regression.example    # tracked example; no real secret
    .env.regression.local      # your local regression key; ignored by Git
```

From the repository root, create your local file and edit it locally:

```sh
cp qa/.env.regression.example qa/.env.regression.local
chmod 600 qa/.env.regression.local
```

Set these values in that file:

```dotenv
REGRESSION_OPENAI_API_KEY=your-regression-key
REGRESSION_OPENAI_MODEL=gpt-4o-mini
REGRESSION_OPENAI_VISION_MODEL=gpt-4.1-mini
REGRESSION_MAX_AI_CALLS=20
REGRESSION_MAX_OUTPUT_TOKENS=2048
REGRESSION_AI_TIMEOUT_SECONDS=45
REGRESSION_MAX_TOTAL_TOKENS=100000
```

The local file is read **only** when passed with `--env-file qa/.env.regression.local`. Alternatively supply these same `REGRESSION_*` variables through your shell/CI secret environment. Environment values override file values. The loader does not expand shell commands or variable references.

There is **no fallback to `OPENAI_API_KEY`**, no application `.env` auto-load and no AWS SSM lookup in the regression runtime. A separate key can be used without modifying the application key. Do not put real keys in the example, test fixtures, command-line arguments or source control.

A key is unnecessary for mock mode. Live mode needs the project's OpenAI/httpx dependencies; use the repository's locked environment (`uv sync`) or install `summary_regression/requirements-live.txt` in an isolated environment. No AWS, Redis, Clerk, Node, LangSmith or database credentials are needed for this pack.

## Inspect without running tests or calling OpenAI

```sh
python3 qa/summary_regression/run_pack.py --mode mock --list
python3 qa/summary_regression/run_pack.py --mode live --list
python3 qa/summary_regression/run_pack.py --mode live \
  --env-file qa/.env.regression.local --check-config
```

`--check-config` checks local configuration only; it does not verify key validity, billing, model permissions or connectivity. No regression or API call is made. The key is never printed.

## Run after fixes and adapter integration

The supplied `adapter_template.py` intentionally raises `NotImplementedError`. Implement it—or supply a reviewed replacement—against the fixed application code. Do not implement an alternate parser/summarizer in the adapter. See the contract for injecting sync/async OpenAI clients and in-memory repositories.

```sh
# Controlled failures: same FastAPI code, mocked AI; no key needed.
python3 qa/summary_regression/run_pack.py --mode mock --execute \
  --adapter /absolute/path/to/implemented_fastapi_adapter.py

# Small real-AI selection against that SAME FastAPI adapter.
python3 qa/summary_regression/run_pack.py --mode live --execute \
  --adapter /absolute/path/to/implemented_fastapi_adapter.py \
  --env-file qa/.env.regression.local --case MIME-03 --case CLIN-04

# Mixed suite: mocked cases plus selected real-AI cases, twice each.
python3 qa/summary_regression/run_pack.py --mode mixed --execute \
  --adapter /absolute/path/to/implemented_fastapi_adapter.py \
  --env-file qa/.env.regression.local --repeat 2
```

Mock and live regressions have been executed; the current report records the latest run. Review the call/output budgets first. The small default call budget may block a full mixed run; start with selected cases, then deliberately raise the budget. The configured output-token ceiling must accommodate the actual application's request limits; the transport rejects oversized requests rather than silently truncating the application's output allowance. SDK retries are disabled; application-level retries count against the same request budget.

The cumulative token threshold stops new calls after reported usage reaches it. An in-flight request can exceed it, especially under concurrency; it is not a dollar spending cap. Reports record actual token usage, requested/returned model IDs, durations and request counts. The client pins the official OpenAI endpoint, disables inherited HTTP proxies and does not use production tracing callbacks.

## Database and result rules

**No production or test database connection, SQL, DDL or migration is permitted.** Storage uses local fixtures; repository behavior is observed in memory. This tests the application's save/preserve/prune decisions but does not prove actual database transaction isolation or locking. Do not use `src/app/tests/conftest.py`, which contains create/drop behavior.

The runner writes only under:

```text
qa/results/report.html
qa/results/report.json
qa/results/outputs/<case>-<mock-or-live>-<iteration>.json
```

Reports distinguish `application_mock` and `application_live`. Live output files contain the adapter's observed pipeline results for review. The adapter must include actual generated summaries and extraction evidence, not just pass/fail booleans. Credentials are redacted and exception messages are not serialized. Open `results/report.html` for the single current report, overwritten each run. Both modes retain full original observed output. Older timestamp directories are historical artifacts and are no longer created. Synthetic documents remain in [`testdata/`](testdata/); report links include MIME type, size, purpose and verified SHA-256.

`PASS`, `FAIL`, `BLOCKED`, `REVIEW_REQUIRED`, `ERROR` and `CANCELLED` remain distinct. Any non-pass causes a nonzero exit status. Reports are checkpointed after each case so earlier results survive interruption.

Adapters are executable Python. Review them before importing them. Ordinary Python network connections are blocked during adapter import and mock execution, but this is not an OS sandbox. Native subprocesses or arbitrary adapters could bypass that guard; prohibit them and use network-restricted execution in CI. In live mode allow OpenAI only and keep all other external dependencies faked.

## Authoring and implementation references

Regenerating fixtures/specifications is separate from regression execution; see the [pack guide](summary_regression/README.md). Never regenerate expected results to make a failing test pass.

The regression client uses the project's existing OpenAI API style; official references: [Chat Completions Python API](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create) and [vision inputs](https://developers.openai.com/api/docs/guides/images-vision). The actual production prompts and validation still come from FastAPI.

## Release readiness

The final resilience audit is in Section 30 of the fix plan. Startup/readiness, overload, full-request deadlines, cleanup/shutdown, changing source manifests, JSON metadata tracking and the actual application adapter are explicit gates. Preparing cases is not a test pass. Implementation and regression execution are in progress. Unwired cases, failures and pending human review remain release gaps; consult the current report.

The implemented pipeline requests up to 4096 output tokens per model call. Set `REGRESSION_MAX_OUTPUT_TOKENS=4096` or higher in your local QA configuration for live runs. Your existing local secret file has not been opened or overwritten.

## Reading the current report

The report includes test purpose, plan references, exact document links, effective configuration and fault injection, every expected assertion and actual observation, original output downloads, case duration, AI usage, pending human review and requirement coverage. Missing observations fail checks; unexecuted checks are marked NOT_EVALUATED. A green selected run does not imply that unselected cases passed. Run with Python 3.12 and the project dependencies.

FHIR JSON is a structured healthcare record, sometimes containing a base64 document attachment with a declared contentType. Its attachment must be decoded and parsed using the relevant document parser before summarization. The synthetic JSON files test this boundary; they are not database records written by regression.

### Do not tune production to synthetic examples

Fixtures are representative examples, not an exhaustive definition of valid clinical content. Application fixes must follow format, encoding, evidence, authorization and failure-containment contracts. Never add production branches for a fixture filename, test ID, sample diagnosis, medication or expected answer. Mock responses and injected failures are test-only. Live model wording can vary; evaluate supported meaning, source coverage and statuses rather than exact prose. A blocked or review-required case is not a pass.

### Interpreting a safe rejection

`SAFELY_REJECTED` means a rejected clinical candidate was withheld, the observed publication payload contains the failure template and empty clinical fields, and the unmet assertions concern summary availability only. Safety containment passed; no summary was produced. The original availability checks remain visible. This is distinct from `FAIL`, and does not claim clinical accuracy, successful summary delivery or a database integration pass. Deliberate unsafe-response injection cases remain `PASS` when all their expected rejection checks pass.

### Approved format policy and runtime dependencies

No added application environment configuration is required. FHIR JSON/XML and multipart are enabled in the internal parser policy. NDJSON, ZIP and gzip document containers produce an unsupported-format message. HTTP Content-Encoding is separate. Legacy text-based `.doc` uses `antiword` plus `olefile`; the Dockerfile packages antiword and the Python dependency is locked. Development/QA environments must have antiword on PATH. Encrypted, macro-bearing or image/embedded-object legacy files remain contained unsupported/password outcomes; no raw fallback is permitted.

The Linux memory-limit regression uses the current Linux interpreter, or on macOS the local `python:3.12-slim` Docker image. The probe runs with networking disabled, read-only source mount, no application credentials and no database. If Docker/image access is absent, that platform qualification is explicitly blocked. It never pulls an image during a mock run.

Prepare the independent reviewer packet after a completed regression:

```sh
python qa/summary_regression/prepare_clinical_review.py
```

[Clinical review packet](CLINICAL_REVIEW.md) and [engineering review evidence](ENGINEERING_REVIEW.md) distinguish clinical approval from code checks. HTTP 401/403 live failures are reported as credential blockers, not application-test integration gaps. Update the existing regression key file locally; never paste the key into a report.

OCR/logo routing regressions are included in the main mock pack as `ROUTING-*`, `ACCESS-EXISTING-*`, and `PRESERVE-*`. Their synthetic documents are under `qa/testdata/routing`. To run only the local unit checks without replacing the canonical full-pack report:

```sh
python -m unittest discover -s qa/summary_regression -p 'test_*safety*.py'
```

See [routing and deferred persistence verification](ROUTING_AND_PERSISTENCE_REVIEW.md) for supported logo geometry, access limitations and the later deployed-instance checklist. Passing memory-backed tests does not verify database transactions or caregiver integration.

To export the completed run for client review without rerunning AI or regression:

```sh
python qa/summary_regression/prepare_client_review.py
```

This overwrites `qa/client_review/` and `qa/client_review.zip`. The portable HTML includes linked synthetic source documents, saved extracted text, returned summaries/messages, and expected-versus-actual checks. Mock OCR/model responses are explicitly labeled and cannot establish live accuracy. The export excludes application code, environment files and runtime logs. Extract the ZIP before opening `client_review/index.html`.
