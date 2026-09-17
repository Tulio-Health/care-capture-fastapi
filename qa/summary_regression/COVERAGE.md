# Fix plan coverage map

This is a specification coverage map, not a test pass report. Execution results are recorded separately in `../results/report.html`; catalog coverage does not establish passing behavior. Case details and exact assertions are in `cases.json`; exact requirement-to-case IDs are in `coverage.json`.

| Requirement | Plan sections | Coverage | Cases |
|---|---|---|---|
| R01 | 1–4, 9 | Every document-to-model path uses the extraction gate | 10 |
| R02 | 2, 11 | Incident: late diagnosis and ordered/performed distinction | 4 |
| R03 | 5–6 | Native format MIME variants and signature routing | 168 |
| R04 | 5 | Unsupported/disabled formats fail explicitly | 59 |
| R05 | 5, 8 | FHIR/NDJSON attachment and container boundaries | 40 |
| R06 | 6 | MIME conflicts, aliases, parameters and termination | 37 |
| R07 | 7 | BOM/code page/Unicode/invalid encoding | 23 |
| R08 | 8, 10 | Malformed/protected/empty files and quality gate | 15 |
| R09 | 8 | Active content, entity expansion and external resources | 6 |
| R10 | 8, A09 | Streaming, worker, memory, page, pixel and archive limits | 11 |
| R11 | 9–10 | Typed results cannot be bypassed by false success | 4 |
| R12 | 11, A08 | Chunk budgets, middle/tail content and final reduction | 8 |
| R13 | 12, 25 | Procedure status, time, subject and evidence | 24 |
| R14 | 13, 24 | No documents versus unreadable, partial and refresh notices | 11 |
| R15 | 14, A01 | No destructive pruning after parse/model/acquisition failure | 3 |
| R16 | 14, A10 | Source isolation, generation order and idempotency in memory | 7 |
| R17 | 15 | Safe diagnostics, distinct metrics and no secret leakage | 3 |
| R18 | 16–17, 19 | Regression inventory, review gates and release criteria | 15 |
| R19 | 18 | Rollback preserves strict gate; no implicit historical jobs | 3 |
| R20 | 20–21 | References and adapter/model support decisions | 59 |
| R21 | A02 | Complete cache mapping; distinguish lookup errors | 4 |
| R22 | A03 | Failed/pending/missing/excluded acquisition and FHIR fallback | 7 |
| R23 | A04 | Model batch failures and ID/cardinality reconciliation | 5 |
| R24 | A05 | Complementary, duplicate and conflicting consolidation facts | 4 |
| R25 | A06 | Completed task preservation, cancellation and save race | 3 |
| R26 | A07, 25.8 | Translation scalar/type/array/prose/metadata integrity | 8 |
| R27 | A11 | Cache source/version/coverage freshness and force refresh | 7 |
| R28 | 23.2 | Lifecycle, outcome and display provenance stay separate | 4 |
| R29 | 23.3–23.4 | Central error policy, retry classification, safe IDs | 16 |
| R30 | 23.5 | Manifest-derived coverage; unknown totals on inventory error | 8 |
| R31 | 23.6–23.9 | Safe HTTP, request/output distinction and persistence failure | 4 |
| R32 | 24 | Existing JSON/text/metadata contracts; no fake procedure rows | 5 |
| R33 | 25.1–25.4 | Shared grounding prompt, provenance and injection rejection | 4 |
| R34 | 25.5–25.7 | Semantic checks, correction bounds and final validated version | 25 |
| R35 | 25.9–25.10 | Clinical omission independent of fabrication | 6 |
| R36 | 26.1–26.3 | Vision capability, page/region routing and model budgets | 51 |
| R37 | 26.4–26.5 | Vision schema/page identity/truncation/crops/fidelity | 7 |
| R38 | 26.6 | Vision errors, escalation and unchanged persistence/display | 5 |
| R39 | 26.7 | Real-model quality review and rollback gates | 2 |
| R40 | 28 / A12 | Final source-review finding A12 | 4 |
| R41 | 28 / A13 | Final source-review finding A13 | 6 |
| R42 | 28 / A14 | Final source-review finding A14 | 3 |
| R43 | 28 / A15 | Final source-review finding A15 | 3 |
| R44 | 28 / A16 | Final source-review finding A16 | 4 |
| R45 | 28 / A17 | Final source-review finding A17 | 2 |
| R46 | 28 / A18 | Final source-review finding A18 | 3 |
| R47 | 28 / A19 | Final source-review finding A19 | 3 |
| R48 | 30.1 | Initialization, optional capabilities and real app construction | 4 |
| R49 | 30.1 | Admission limits and process/replica budgets | 2 |
| R50 | 30.1 | Whole-request deadline and bounded preparation/pool waits | 2 |
| R51 | 30.1 | Cleanup, worker failure, shutdown and scheduler ownership | 4 |
| R52 | 30.1 | Source snapshot and membership consistency | 2 |
| R53 | 30.1 | JSON mutation, legacy metadata and real serialization | 4 |
| R54 | 30.1 | Actual pipeline adapter, QA key isolation and report failures | 3 |

## Explicit limits

The target is comprehensive coverage of the current fix plan. No finite corpus covers every possible MIME string, encoding, corrupt byte sequence or clinical expression. New incidents and enabled adapters must add fixtures and assertions.

The default pack prohibits database access. In-memory cases cover service persistence decisions and controlled interleavings, not actual database isolation/locking. Those properties are not certified by this pack.

Optional adapter ON cases are conditional specifications; unsupported/OFF tests cover containment now. Genuine legacy DOC/HEIC, encrypted DOCX, handwriting and multilingual scan positive-quality corpora are still needed before enabling those adapters or making quality claims. Signature-only files are explicitly labeled negative-only.

Live-model fidelity, bilingual review and mobile display are review gates, not inferred from mocked results. The integration adapter is intentionally unimplemented until the fixes land. See RELEASE_CHECKLIST.md.
