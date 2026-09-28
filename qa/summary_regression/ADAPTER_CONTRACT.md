# FastAPI regression adapter contract

## Entry point

Implement a local Python module exposing:

```python
PERSISTENCE_MODE = "memory"
SUPPORTED_MODES = {"mock", "live"}

def run_case(case: dict, fixture_dir: Path, context) -> dict:
    # Call the real fixed application code with isolated dependencies.
    # Return observed execution/persistence data in the QA projection below.
    ...
```

The adapter must declare `PERSISTENCE_MODE = "memory"`. No real database connections, SQL execution, writes, schema operations or migrations are allowed. Import-safe repository code may be exercised with in-memory session boundaries. All persistence behavior is exercised against an in-memory fake repository and measured with spies. Run reports are written only by the runner to `qa/results/` (one overwritten `report.html` and `report.json`, with stable per-case output paths).

The runner calls this synchronous entry point sequentially. An adapter may use `asyncio.run` for async service code and create concurrent tasks inside a concurrency case. Every case must create a fresh temporary directory, fake storage, spy model client, clock and repository state. Restore all patches and close resources after each case.

Do not implement a second parser or summarizer in the adapter. Do not echo `case['expected']` into the observation. Do not let mocks return the expected complete summary except where a case specifically provides a canned model response. Real application validation, state transitions and persistence decisions must execute.

The test harness is an internal projection, not a new endpoint/response envelope or database schema. Map actual typed outcomes/error codes to the canonical plan vocabulary in one documented place. If implementation uses a different justified code, review the oracle mapping; do not weaken failure checks to make tests pass.

## Inputs

- `fixtures`: paths relative to `qa/testdata/`, all synthetic. Documents and JSON support data are distinguished using the catalog and case purpose; do not submit metadata JSON to a clinical summarizer as an attachment.
- `config`: per-case settings, such as declared MIME override, absent filename, vision flag, source, token/page/pixel/read budgets, retry limit, source version or target language.
- `inject`: explicit external-boundary behavior. Implement each injected condition with a fake dependency or controlled clock, not by manufacturing final status.
- `expected`: oracle evaluated by the runner, not operational input.
- `manual_review`: required human checks. Return `manual_review_completed: true` only after recorded review, never by default.

Source document order is fixture order unless a case specifies timestamps or source IDs. Use deterministic synthetic IDs (`doc-a`, `doc-b`, ...) and known fixture lengths. Seed `prior_state.json` where requested. Populate current source/version metadata consistently for cache-hit cases; then change only the field being tested for invalidation cases.

## Fault injection mapping

| Specification | Required harness behavior |
|---|---|
| `parser: raise:rtf/html` | Patch the library/parser boundary to throw; execute real extraction error handling |
| `download` | Fake streamed response with stated length and repeated fixture chunks; measure actual bytes read |
| `download_redirect` | Simulate redirect in FastAPI-owned fetch boundary; spy on destination and headers |
| `inventory: raise` | Repository inventory query raises; no false empty-list result |
| `model_chunk_ordinal` / `model_batch_ordinal` | One-based failing call ordinal after actual chunking/batching |
| `model_error` / `model_error_sequence` | Typed timeout/rate-limit failures at the model client boundary |
| `model_response_key` | Canned unsafe response from `model_responses.json`; pass through real validation |
| `repeat_on_correction` | Correction attempt returns the same unsafe response to test bounded failure |
| `vision_response: gold_transcription` | Mock transcription only using `scan_gold.json`; still run extraction validation and downstream logic |
| `vision: unreadable/timeout_always` | Return typed unreadable output or raise timeout on every attempt |
| `vision_response_key` | Canned invalid vision result from `model_responses.json` |
| `vision_omit_page` | Omit this page from response despite a complete server-generated page manifest |
| `translation_response_key(s)` | Inject altered scalar/prose output after supplying original source |
| `prior_validation: invalid` | Seed explicit invalidation metadata; do not relabel old content as last-good |
| `prior_summary_kind: placeholder` | Seed deterministic error text and placeholder metadata |
| `extraction_outcome: successful_no_procedures` | Simulate an authoritative successful extraction with no procedures, distinct from parse failure |
| `attempts` | Run jobs with declared source versions and completion order; inspect winner and rows |
| `task_delays_ms` | One service completes while another exceeds aggregate timeout; capture each source result |
| `download_delay_ms` | Delay storage boundary while a heartbeat coroutine runs; measure responsiveness |
| `persistence: unavailable` | Fake repository raises a DB availability error on save |
| `exception_key` | Throw error carrying QA canary text; inspect display and normal logs for leaks |

If a requested injection/observation is not wired, raise `NotImplementedError` and report BLOCKED. Never silently ignore unsupported config keys.

## Observations

Only fields required by the selected case need be present. Missing required fields fail. Each observation must derive from a spy, actual return value, validated facts, or resulting fake repository state.

| Group | Meaning and measurement |
|---|---|
| `outcome` | Normalized terminal outcome: success, partial, unavailable, no_documents |
| `extraction` | Actual adapter, extracted text, success state, MIME mismatch |
| `calls` | Separate counters for vision extraction, clinical summarization, all model calls, DOCX parser, external-resource and unapproved fetches |
| `model_input` | Captured validated text across calls and transcript segment order; do not read original fixtures to synthesize this observation |
| `boundary` | Raw-content bypass, secret leakage, credential forwarding, placeholder use and order of vision-validation/summarization events |
| `coverage` | Expected/accepted/failed pages, documents, chunks and model batches, duplication and completeness, derived from actual manifest/outcomes |
| `clinical` | Clinical facts from accepted output: statuses, timelines, active drugs, doses, labs, retained facts and unsupported claim count |
| `display` | Actual returned/persisted summary text, display kind, notice count and translated warning preservation |
| `persistence` | Before/after rows, source preservation, pruning ownership, duplicate count, DDL calls, winning version and save result |
| `cache` | Whether actual service reused a prior result and retained required fields |
| `translation` | Validation decision and whether original validated content survived failure |
| `sources` | Per-source terminal outcome, including completed work during another task's timeout |
| `resources` / `io` | Measured call budgets, bytes read, offloading responsiveness, sandbox writes and enforced limits |
| `error_codes` | Actual errors mapped to approved stable codes, not user-facing exception strings |
| `http.status` | Actual status produced by route/error mapping under test |
| `logs.text` | Captured ordinary logs from synthetic case only |
| `evaluation` | Recorded independent real-model review and predeclared threshold results |

`boundary.raw_content_forwarded` refers to raw markup/binary/unvalidated content entering **clinical summarization**. Images supplied to the dedicated vision extraction stage are permitted. Assert validation occurs before the first clinical summarization call; a counter alone cannot prove ordering.

`clinical.unsupported_claims_published` requires comparison of the actual accepted claims against the fixture's clinical facts. It is not the model's own self-rating. For adversarial canned responses, verify rejection/correction before persistence. A text substring check alone cannot distinguish “no pneumonia” from a confirmed diagnosis.

For all-failed cases, `calls.summarization == 0` does not imply `calls.vision == 0`: extraction may have been attempted. Parser corruption before vision routing must produce zero content model calls. Keep these boundaries explicit.

## Persistence and UI verification

Seed fake rows from `prior_state.json`, snapshot them, invoke the actual service, then compare results. Preserve unrelated metadata and other summary sources. Re-run failed refresh cases twice to catch duplicate notices. Model validation failures must never persist unsafe drafts.

Do not connect to any database, including a disposable test database. In-memory interleaving cases test service decisions only; they do not prove database transaction isolation or locking. Record that limitation instead of adding database access. Do not use the repository's current autouse create/drop fixture.

Mobile compatibility is initially assessed from the unchanged summary JSON/text contract. After implementation, manually verify no-documents, unavailable, partial and refresh-failed text in the current mobile app using synthetic data. This pack does not claim a UI automation pass.

## Harness limits

`run_pack.py` is not a security sandbox. A supplied adapter is executable Python. Review it, disable network in deterministic tests, and avoid all database credentials. The memory-mode declaration alone cannot sandbox arbitrary adapter code; inspect dependencies and use a network-restricted process for execution. Supply an outer process timeout in CI to catch hung native parsers; the assertion runner cannot safely terminate arbitrary in-process work.

The runner has no dependencies beyond Python's standard library. The fixed application adapter will need the project's pinned dependencies in a separate test environment. The fixture-generation dependency file is not a replacement for the application's lockfile.

## Same FastAPI implementation in both modes

`context.mode` is `mock` or `live`. Both must call the same actual fixed FastAPI functions. Do not add a separate evaluation summarizer or duplicate application parsing/validation logic. The live profile selects IDs from the existing case catalog.

- In mock mode, inject canned model responses at the client boundary. Ordinary socket connections are blocked.
- In live mode, inject SDK clients from `context.ai.make_async_client()` / `make_client()` into the actual application's model factory. For PydanticAI, supply the async client to its OpenAI provider; for LangChain, supply the corresponding SDK completion clients through supported dependency injection. Keep real prompts, schemas, validators and orchestration. Pin compatible dependencies through the application lockfile.
- Match the actual application's models to the explicit regression configuration. Every real inference must go through the injected budgeted transport. A live case making no counted AI calls is an error, never a pass.
- Set actual request output limits within the declared QA budget. Do not silently lower a production setting to obtain a pass; report the configuration and use a sufficient explicit cap.
- Close each injected SDK client in the adapter's `finally` block, including async clients.
- Override app settings and external dependencies before importing services so `.env`, SSM, Redis, DB and telemetry do not initialize. Do not export the QA key into the production `OPENAI_API_KEY` variable.
- Gold transcripts and clinical oracle files are only for assertions. Live mode must obtain text from actual parser/vision extraction, never from gold data.
- Return `pipeline_output` with actual generated summary JSON, extracted content/provenance and versions for synthetic inputs. The runner saves the returned observations under `qa/results/`; no DB writes.
- Set `manual_review_completed` only after recorded independent review. Do not derive it from a model's confidence or self-evaluation.

The default application_adapter.py now exercises real parsing/OCR/attachment chains with injected model clients. The full orchestration/persistence/fault matrix is not yet wired; unsupported controls report BLOCKED. The current execution statuses are recorded in `../results/report.html`. See ../IMPLEMENTATION_STATUS.md.
