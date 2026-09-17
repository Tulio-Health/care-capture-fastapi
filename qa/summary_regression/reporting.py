"""Offline, escaped, current-run report. No database or network access."""
from collections import Counter
from html import escape
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote


def pretty(value):
    return escape(json.dumps(value, indent=2, ensure_ascii=False))


def fixture_inventory(root):
    catalog = json.loads((root / 'fixture_catalog.json').read_text())['fixtures']
    result = {}
    for name, metadata in catalog.items():
        path = root / metadata['path']
        exists = path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        result[name] = {**metadata, 'exists': exists, 'actual_sha256': digest,
                        'integrity': 'PASS' if exists and digest == metadata['sha256'] and path.stat().st_size == metadata['bytes'] else 'FAIL',
                        'href': quote(os.path.relpath(path, root.parent / 'results'), safe='/')}
    return result


def render(report):
    rows = report['cases']
    counts = report['counts']
    fixtures = report['fixtures']
    complete = report['state'] == 'completed' and len(rows) == report['planned_executions']
    green = complete and all(r['status'] == 'PASS' for r in rows) and bool(rows) and all(f['integrity'] == 'PASS' for f in fixtures.values())
    health = 'GREEN — selected scope passed' if green else 'NOT CLEAR — failures, gaps, reviews or incomplete execution remain'
    def doc_link(name):
        f = fixtures.get(name)
        return f'<a href="{escape(f["href"], quote=True)}">{escape(name)}</a> ({escape(f["mime"])}; {f["bytes"]} bytes; integrity {f["integrity"]})' if f else escape(name) + ' — MISSING FROM CATALOG'
    blocked = [r for r in rows if r['status'] == 'BLOCKED']
    unresolved = '<h2>Blocked scenarios</h2><p>These scenarios have not been verified. Each row identifies the missing integration or execution prerequisite.</p><table><tr><th>Case</th><th>What remains unverified</th><th>Reason</th></tr>' + ''.join('<tr><td>' + escape(r['id']) + '</td><td>' + escape(r['title']) + '</td><td>' + escape(str(r.get('reason', 'Unspecified'))) + '</td></tr>' for r in blocked) + '</table>'
    review_rows = []
    for r in rows:
        if r['status'] != 'REVIEW_REQUIRED':
            continue
        notes = ' '.join(r['manual_review'])
        kind = 'Engineering review'
        if r['scope'] == 'application_live' or 'Real-model' in notes:
            kind = 'Live clinical/OCR accuracy review'
        elif r['id'].startswith('TRANSPORT-'):
            kind = 'Optional-adapter rollout decision'
        elif r['id'] == 'PARSE-05':
            kind = 'Unsupported legacy capability: negative fixture only'
        review_rows.append('<tr><td>' + escape(r['id']) + '</td><td>' + kind + '</td><td>' + escape(notes) + '</td></tr>')
    unresolved += '<h2>Reviews still required</h2><p>Automated assertions passed for these rows, but the listed review is outstanding. Configuration and engineering reviews are distinguished from clinical accuracy review. A canned AI response does not establish real-model accuracy.</p><table><tr><th>Case</th><th>Review type</th><th>Required evidence or decision</th></tr>' + ''.join(review_rows) + '</table>'
    cards = []
    for r in rows:
        checks = ''.join('<tr><td>' + escape(c['path']) + '</td><td>' + escape(c['op']) + '</td><td><pre>' + pretty(c['expected']) + '</pre></td><td><pre>' + pretty(c['actual']) + '</pre></td><td>' + c['status'] + '</td></tr>' for c in r.get('checks', []))
        files = '<ul>' + ''.join('<li>' + doc_link(n) + '</li>' for n in r['fixtures']) + '</ul>' if r['fixtures'] else '<p>No document fixture: control or service behavior test.</p>'
        output = '<a href="' + escape(r['output_file'], quote=True) + '">Complete original observed output (JSON)</a>' if r.get('output_file') else 'No pipeline output returned; see execution reason.'
        cards.append(f'''<details class="case" data-status="{r['status']}"><summary>{escape(r['id'])} · {escape(r['scope'])} · iteration {r['iteration']} · <b>{r['status']}</b> — {escape(r['title'])}</summary>
<p>Plan references: {escape(str(r['plan_refs']))}. Duration: {r.get('duration_seconds', 0)} seconds.</p>{files}
<p>{output}</p><p>Outcome dimensions (independent of the case's expected behavior):</p><pre>{pretty(r.get('outcome_assessment', {}))}</pre><p>Execution reason: {escape(str(r.get('reason', r.get('exception_type', 'None'))))}</p>
<details><summary>Configuration and injected conditions</summary><pre>{pretty({'config': r['config'], 'inject': r['inject']})}</pre></details>
<table><thead><tr><th>What was checked</th><th>Operator</th><th>Expected output</th><th>Actual output / observation</th><th>Verdict</th></tr></thead><tbody>{checks}</tbody></table>
<details><summary>Additional failures and human review checklist</summary><pre>{pretty({'failures': r.get('failures', []), 'manual_review': r['manual_review']})}</pre></details></details>''')
    groups = []
    for g in report['requirements']:
        matching = [r for r in rows if r['id'] in g['case_ids']]
        missing = set(g['case_ids']) - {r['id'] for r in matching}
        groups.append('<tr><td>' + escape(g['id']) + '</td><td>' + escape(g['requirement']) + '</td><td>' + escape(str(dict(Counter(r['status'] for r in matching)))) + '</td><td>' + escape(', '.join(sorted(missing)) or 'None') + '</td></tr>')
    inventory = ''.join('<tr><td>' + doc_link(n) + '</td><td>' + escape(f['purpose']) + '</td><td><code>' + escape(str(f['actual_sha256'])) + '</code></td></tr>' for n, f in fixtures.items())
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Summary regression report</title>
<style>body{font:15px system-ui;margin:2rem;line-height:1.5;color:#172435}table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border:1px solid #ccc;padding:.5rem;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:24rem;overflow:auto}details{border:1px solid #ccc;padding:.7rem;margin:.7rem 0}summary{cursor:pointer}code{overflow-wrap:anywhere}input,select{padding:.6rem;margin:.5rem}a{color:#0759a5}.health{background:#fff0c2;padding:1rem}</style>
<h1>Summary parsing and AI regression</h1>''' + f'''<p class="health"><strong>{health}</strong></p><p>Run {escape(report['run_id'])} · {escape(report['state'])} · mode {escape(report['mode'])} · updated {escape(report['updated_at'])}</p>
<p>This single report is overwritten on every execution. Synthetic documents remain stored in the fixture folder. Results use memory persistence; no database writes. Mock tests exercise application code with deterministic AI responses. Live tests use the regression AI key. Passing mocks does not establish clinical accuracy or mobile/production readiness.</p>
<p>{len(rows)} / {report['planned_executions']} selected executions recorded; {len(set(r['id'] for r in rows))} / {report['pack_case_count']} pack cases represented. {report['not_selected_case_count']} pack cases not selected.</p><pre>{pretty(counts)}</pre>
<p>PASS means declared automated checks passed. SAFELY_REJECTED means containment passed but no summary was produced. REVIEW_REQUIRED means human review remains. BLOCKED is untested, not passed. Missing observations fail checks. Health covers selected scope only; requirement gaps are listed below.</p>
<h2>Safety containment versus summary generation</h2><p>SAFELY_REJECTED means validation worked: the rejected candidate was withheld and the observed publication payload contains only the failure template with empty clinical fields. No summary was produced. The original summary-availability assertion results remain visible; this is not an unsafe-output failure. A deliberately injected unsafe response passes when its expected rejection checks pass. The dimensions below do not override the original assertions or human-review requirements. NOT_ASSESSED does not mean safe.</p><h2>AI usage and execution boundary</h2><pre>{pretty({'scope': report['scope'], 'adapter': report['application_adapter'], 'ai': report['ai']})}</pre>
<h2>FHIR JSON explained</h2><p>FHIR is a healthcare data exchange format. A JSON record may contain structured clinical fields or an attached document encoded as base64 with a contentType. These fixtures test safe decoding and format-specific parsing of that attachment before AI summarization. JSON is the envelope; its attachment might be RTF, PDF, text or an image. The fixture links show the exact synthetic input.</p>
{unresolved}<h2>Test results</h2><input id="search" placeholder="Search cases, documents or checks" aria-label="Search cases"><select id="status" aria-label="Filter status"><option value="">All statuses</option>''' + ''.join('<option>' + s + '</option>' for s in counts) + '</select>' + ''.join(cards) + '''<h2>Requirement coverage</h2><p>Counts represent executed case/mode combinations; missing IDs were not executed in this run. A requirement is not qualified merely because its cases exist.</p><table><tr><th>Requirement</th><th>Description</th><th>Observed verdicts</th><th>Unexecuted case IDs</th></tr>''' + ''.join(groups) + '''</table><h2>Stored synthetic document inventory</h2><p>Hashes and sizes are checked against the fixture catalog. Documents are retained across runs, including binary and malformed test files; open with the appropriate local viewer.</p><table><tr><th>Document reference / MIME / integrity</th><th>Purpose</th><th>Actual SHA-256</th></tr>''' + inventory + '''</table><p><a href="report.json">Machine-readable current report</a></p>
<script>const q=document.querySelector('#search'),s=document.querySelector('#status');function filter(){document.querySelectorAll('.case').forEach(e=>e.hidden=!!((s.value&&e.dataset.status!==s.value)||!e.textContent.toLowerCase().includes(q.value.toLowerCase())))}q.addEventListener('input',filter);s.addEventListener('change',filter)</script></html>'''


def write_report(directory, report):
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [('report.json', json.dumps(report, indent=2, ensure_ascii=False) + '\n'), ('report.html', render(report))]:
        temporary = directory / (name + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(directory / name)
