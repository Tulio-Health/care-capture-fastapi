#!/usr/bin/env python3
"""Build documentation from case specifications; never execute a case."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
cases=json.loads((ROOT/'cases.json').read_text())['cases']
requirements=[
 ('R01','1–4, 9','Every document-to-model path uses the extraction gate',['GATE-','CONTRACT-','PARSE-01','PARSE-02','VISION-BOUNDARY']),
 ('R02','2, 11','Incident: late diagnosis and ordered/performed distinction',['LONG-01','LONG-02','CLIN-01','CLIN-03']),
 ('R03','5–6','Native format MIME variants and signature routing',['FMT-','ALIAS-','MIME-','RTF-MIME-']),
 ('R04','5','Unsupported/disabled formats fail explicitly',['UNSUPPORTED-','TRANSPORT-','PARSE-05']),
 ('R05','5, 8','FHIR/NDJSON attachment and container boundaries',['TRANSPORT-','FHIR-','NDJSON-','GZIP-','ZIP-']),
 ('R06','6','MIME conflicts, aliases, parameters and termination',['MIME-','RTF-MIME-','ALIAS-']),
 ('R07','7','BOM/code page/Unicode/invalid encoding',['ENC-','RTF-ENC-','RTF-UC-']),
 ('R08','8, 10','Malformed/protected/empty files and quality gate',['PARSE-','ERR-EMPTY','RTF-EMPTY','ENC-REJECT-']),
 ('R09','8','Active content, entity expansion and external resources',['HTML-ACTIVE','XML-DTD','SEC-']),
 ('R10','8, A09','Streaming, worker, memory, page, pixel and archive limits',['LIMIT-','ZIP-','VISION-PIXELS','A09-','CANCEL-WORKER']),
 ('R11','9–10','Typed results cannot be bypassed by false success',['CONTRACT-','ERROR-COVERAGE','GROUND-WRONGPAGE']),
 ('R12','11, A08','Chunk budgets, middle/tail content and final reduction',['LONG-','A08-']),
 ('R13','12, 25','Procedure status, time, subject and evidence',['CLIN-','GROUND-']),
 ('R14','13, 24','No documents versus unreadable, partial and refresh notices',['UI-','DATA-01','DATA-02']),
 ('R15','14, A01','No destructive pruning after parse/model/acquisition failure',['DATA-03','A01-']),
 ('R16','14, A10','Source isolation, generation order and idempotency in memory',['DATA-04','DATA-05','A10-','ERROR-PERSISTRETRY']),
 ('R17','15','Safe diagnostics, distinct metrics and no secret leakage',['ERR-LOG','MONITOR-','ERROR-CORRELATION']),
 ('R18','16–17, 19','Regression inventory, review gates and release criteria',['VISION-REVIEW','DOCX-TABLE','POLICY-']),
 ('R19','18','Rollback preserves strict gate; no implicit historical jobs',['ROLLOUT-','VISION-ROLLBACK']),
 ('R20','20–21','References and adapter/model support decisions',['TRANSPORT-','UNSUPPORTED-','VISION-REVIEW']),
 ('R21','A02','Complete cache mapping; distinguish lookup errors',['A02-']),
 ('R22','A03','Failed/pending/missing/excluded acquisition and FHIR fallback',['A03-']),
 ('R23','A04','Model batch failures and ID/cardinality reconciliation',['A04-']),
 ('R24','A05','Complementary, duplicate and conflicting consolidation facts',['A05-']),
 ('R25','A06','Completed task preservation, cancellation and save race',['A06-','CANCEL-COMMIT']),
 ('R26','A07, 25.8','Translation scalar/type/array/prose/metadata integrity',['A07-','UI-04']),
 ('R27','A11','Cache source/version/coverage freshness and force refresh',['A11-']),
 ('R28','23.2','Lifecycle, outcome and display provenance stay separate',['ERROR-STATUS','ERROR-PREVIOUS','CANCEL-']),
 ('R29','23.3–23.4','Central error policy, retry classification, safe IDs',['POLICY-','ERROR-CORRELATION','ERR-RETRY','ERR-NORETRY']),
 ('R30','23.5','Manifest-derived coverage; unknown totals on inventory error',['ERROR-UNKNOWNCOUNTS','ERROR-COVERAGE','A04-','VISION-COVERAGE']),
 ('R31','23.6–23.9','Safe HTTP, request/output distinction and persistence failure',['ERROR-REQUEST','ERROR-MODEL422','ERR-DB','ERROR-UNEXPECTED']),
 ('R32','24','Existing JSON/text/metadata contracts; no fake procedure rows',['UI-CONTRACT','UI-PROCEDURELIST','ERR-NONE','META-BOUNDED','ERR-METADATA']),
 ('R33','25.1–25.4','Shared grounding prompt, provenance and injection rejection',['SEC-03','CLIN-OFFSETS','GROUND-WRONGPAGE','CLIN-QUOTESEMANTICS']),
 ('R34','25.5–25.7','Semantic checks, correction bounds and final validated version',['CLIN-','ERR-INVALIDJSON','GROUND-','CLIN-POSTPROCESS']),
 ('R35','25.9–25.10','Clinical omission independent of fabrication',['CLIN-OMISSION','LONG-','VISION-REVIEW']),
 ('R36','26.1–26.3','Vision capability, page/region routing and model budgets',['OCR-','VISION-REGION','VISION-TIFF','VISION-PIXELS','VISION-BUDGET','FMT-PNG','FMT-JPEG','FMT-TIFF','FMT-WEBP']),
 ('R37','26.4–26.5','Vision schema/page identity/truncation/crops/fidelity',['VISION-PAGEID','VISION-TRUNCATED','VISION-CONFIDENCE','VISION-CROP','VISION-COORDS','VISION-TABLE','VISION-ROTATED']),
 ('R38','26.6','Vision errors, escalation and unchanged persistence/display',['VISION-TIMEOUT','VISION-ESCALATE','VISION-OFF','DATA-01','UI-03']),
 ('R39','26.7','Real-model quality review and rollback gates',['VISION-REVIEW','VISION-ROLLBACK']),
]
for n in range(12,20):
    requirements.append((f'R{n+28:02d}','28 / A'+str(n),'Final source-review finding A'+str(n),['A'+str(n)+'-']))
requirements += [
 ('R48','30.1','Initialization, optional capabilities and real app construction',['RES-OPTIONAL','RES-MANDATORY','RES-STARTUP','RES-FACTORY']),
 ('R49','30.1','Admission limits and process/replica budgets',['RES-OVERLOAD','RES-WORKERBUDGET']),
 ('R50','30.1','Whole-request deadline and bounded preparation/pool waits',['RES-PREPDEADLINE','RES-POOLWAIT']),
 ('R51','30.1','Cleanup, worker failure, shutdown and scheduler ownership',['RES-CLEANUP','RES-WORKERCRASH','RES-SHUTDOWN','RES-SCHEDULER']),
 ('R52','30.1','Source snapshot and membership consistency',['RES-SOURCECHANGE','RES-MEMBERSHIP']),
 ('R53','30.1','JSON mutation, legacy metadata and real serialization',['RES-JSONDIRTY','RES-LEGACYMETA','RES-SERIALIZE','RES-ALIASES']),
 ('R54','30.1','Actual pipeline adapter, QA key isolation and report failures',['RES-ADAPTER','RES-QAKEY','RES-REPORTIO']),
]
rows=[]
for id,refs,description,prefixes in requirements:
    selected=[c['id'] for c in cases if any(c['id'].startswith(p) for p in prefixes)]
    if not selected: raise ValueError('Unmapped requirement '+id)
    rows.append({'id':id,'plan_sections':refs,'requirement':description,'case_ids':selected,'status':'specification_only'})
(ROOT/'coverage.json').write_text(json.dumps({'status':'specification_only','requirements':rows},indent=2)+'\n')
lines=['# Fix plan coverage map','','This is a specification coverage map, not a test pass report. Execution results are recorded separately in `../results/report.html`; catalog coverage does not establish passing behavior. Case details and exact assertions are in `cases.json`; exact requirement-to-case IDs are in `coverage.json`.','', '| Requirement | Plan sections | Coverage | Cases |','|---|---|---|---|']
for r in rows: lines.append(f"| {r['id']} | {r['plan_sections']} | {r['requirement']} | {len(r['case_ids'])} |")
lines += ['', '## Explicit limits', '',
 'The target is comprehensive coverage of the current fix plan. No finite corpus covers every possible MIME string, encoding, corrupt byte sequence or clinical expression. New incidents and enabled adapters must add fixtures and assertions.', '',
 'The default pack prohibits database access. In-memory cases cover service persistence decisions and controlled interleavings, not actual database isolation/locking. Those properties are not certified by this pack.', '',
 'Optional adapter ON cases are conditional specifications; unsupported/OFF tests cover containment now. Genuine legacy DOC/HEIC, encrypted DOCX, handwriting and multilingual scan positive-quality corpora are still needed before enabling those adapters or making quality claims. Signature-only files are explicitly labeled negative-only.', '',
 'Live-model fidelity, bilingual review and mobile display are review gates, not inferred from mocked results. The integration adapter is intentionally unimplemented until the fixes land. See RELEASE_CHECKLIST.md.']
(ROOT/'COVERAGE.md').write_text('\n'.join(lines)+'\n')
lines=['# MIME and format regression matrix','','This matrix specifies scenarios; current execution results are in `../results/report.html`. Supported/unsupported status is controlled by the explicit case profile, not implied by a file extension. Binary MIME charset parameters do not authorize decoding binary containers as text.','', '| Case | Input | Declared MIME / profile |','|---|---|---|']
for c in cases:
    if c['id'].startswith(('FMT-','ALIAS-','UNSUPPORTED-','TRANSPORT-','RTF-MIME-','MIME-')):
        mime=c['config'].get('declared_mime','fixture declaration')
        lines.append(f"| {c['id']} | {', '.join(c['fixtures'])} | `{mime}` |")
(ROOT/'MIME_FORMAT_MATRIX.md').write_text('\n'.join(lines)+'\n')
print('Wrote coverage documentation only; no regressions executed.')
