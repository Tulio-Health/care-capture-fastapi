"""Export only current manual-review cases as a self-contained offline HTML ZIP."""
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote, unquote
import zipfile
from html.parser import HTMLParser

QA = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((QA / 'results/report.json').read_text())
    if report['state'] != 'completed':
        raise RuntimeError('A completed regression is required')
    cases = [row for row in report['cases'] if row['status'] == 'REVIEW_REQUIRED']
    files = {}
    cards = []
    navigation = []
    escape = html.escape

    def pre(value, empty='No output recorded for this field.'):
        if value is None or value == '':
            return '<p class="muted">' + escape(empty) + '</p>'
        return '<pre>' + escape(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)) + '</pre>'

    for number, row in enumerate(cases, 1):
        saved = json.loads((QA / 'results' / row['output_file']).read_text())
        if saved['run_id'] != report['run_id']:
            raise ValueError('Stale observation')
        observed = saved.get('original_observed_output') or {}
        clinical = bool(row['fixtures'])
        category = 'Clinical / document review' if clinical else 'Access / persistence review'
        links = []
        for name in row['fixtures']:
            fixture = report['fixtures'][name]
            source = (QA / 'summary_regression' / fixture['path']).resolve()
            if not source.is_relative_to(QA / 'testdata'):
                raise ValueError('Invalid source path')
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != fixture['sha256']:
                raise ValueError('Source changed: ' + name)
            files['documents/' + name] = content
            label = name + (' — mock reference text, not a source scan' if name == 'scan_gold.json' else '')
            links.append(f'<li><a href="documents/{quote(name, safe="/")}">{escape(label)}</a></li>')
        identity = escape(row['id'])
        title = escape(row['title'])
        navigation.append(f'<li><a href="#{identity}">{number}. {identity} — {title}</a><span>{category}</span></li>')
        cards.append(f'<section id="{identity}"><p class="eyebrow">{category} · Item {number} of {len(cases)}</p><h2>{identity} — {title}</h2><p class="badge">Manual review pending</p>')
        cards.append('<h3>What needs review</h3><ul>' + ''.join('<li>' + escape(note) + '</li>' for note in row['manual_review']) + '</ul>')
        if clinical:
            cards.append('<h3>Source documents</h3><ul>' + ''.join(links) + '</ul>')
            cards.append('<p class="muted">Files open in your browser or a compatible local application. Mock reference files are labeled separately.</p>')
            text = (observed.get('extraction') or {}).get('text')
            summary = (observed.get('pipeline_output') or {}).get('summary')
            narrative = summary.get('clinical_summary') if isinstance(summary, dict) else summary
            cards.append('<div class="columns"><div><h3>Recorded extracted text</h3>' + pre(text) + '</div><div><h3>Returned test summary</h3>' + pre(narrative, 'No summary was returned; see the recorded outcome below.') + '</div></div>')
            cards.append('<h3>Displayed message / outcome</h3>' + pre(observed.get('display')))
            cards.append('<details><summary>Complete returned summary fields</summary>' + pre(summary) + '</details>')
            cards.append('<p><strong>Review focus:</strong> source-to-text fidelity, table associations, numbers and units, negation, missing or added facts, medication status, and ordered versus performed. Mock outputs cannot establish live OCR/model accuracy.</p>')
        else:
            cards.append('<p>This is an engineering integration review. There is no source document or clinical summary for this case. Local tests passed; deployed behavior remains unverified.</p><h3>Recorded local test evidence</h3>' + pre(observed.get('regression')))
        check_rows = []
        for check in row.get('checks', []):
            check_rows.append('<tr><td>' + escape(check['path']) + '</td><td>' + escape(check['op']) + '</td><td>' + pre(check.get('expected')) + '</td><td>' + pre(check.get('actual')) + '</td><td>' + escape(check['status']) + '</td></tr>')
        cards.append('<details><summary>Automated expectations and actual results</summary><div class="scroll"><table><thead><tr><th>Check</th><th>Comparison</th><th>Expected</th><th>Actual</th><th>Result</th></tr></thead><tbody>' + ''.join(check_rows) + '</tbody></table></div></details>')
        cards.append('<p class="feedback"><strong>Please provide feedback:</strong> case ID, source page/section if applicable, discrepancy, expected result, and reviewer name. Return comments by email; this offline page does not submit or save responses.</p><a href="#contents">Back to list</a></section>')
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Manual review — document processing</title><style>
body{font:16px/1.6 system-ui,sans-serif;color:#182536;background:#f5f7fa;margin:0}main{max-width:1180px;margin:auto;padding:32px 24px}h1{font-size:32px;line-height:1.2}h2{font-size:23px}h3{font-size:17px}a{color:#135dad}section,nav{background:white;border:1px solid #d9e0e7;border-radius:10px;padding:24px;margin:24px 0;scroll-margin-top:20px}.notice{background:#fff3ce;border-left:5px solid #b77b00;padding:18px}.eyebrow,.muted,nav span{color:#526175}.eyebrow{font-size:13px;text-transform:uppercase}.badge{display:inline-block;background:#fff3ce;padding:3px 10px;border-radius:5px}nav li{margin:12px 0}nav span{display:block;font-size:13px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.columns>div{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f9;padding:14px;font:14px/1.5 ui-monospace,monospace}summary{cursor:pointer;font-weight:600}details{margin:18px 0}table{border-collapse:collapse;width:100%}th,td{padding:10px;border:1px solid #d9e0e7;text-align:left;vertical-align:top}.scroll{overflow:auto}.feedback{border-top:1px solid #ddd;padding-top:16px}@media(max-width:760px){.columns{grid-template-columns:1fr}main{padding:16px}section{padding:16px}}@media print{body{background:white}section{break-before:page}.notice{border:1px solid #999}}
</style></head><body><main><h1>Document processing: manual review</h1>'''
    page += f'<p>{len(cases)} review items only · 6 clinical/document reviews and 3 access/persistence reviews.</p><p class="muted">Source regression: {escape(report["run_id"])}</p>'
    page += '<div class="notice"><strong>MOCK regression evidence — not live clinical accuracy validation.</strong><p>Native parsing uses application code. OCR transcriptions and AI summaries use controlled mock responses. Passing automated checks does not complete the manual review. All included documents are synthetic.</p></div><nav id="contents"><h2>Review list</h2><ol>' + ''.join(navigation) + '</ol></nav>' + ''.join(cards) + '</main></body></html>'
    files['index.html'] = page.encode()
    files['README.txt'] = b'Extract the entire ZIP, then open index.html in a browser. Keep documents/ alongside index.html. Only the nine cases marked REVIEW_REQUIRED are included. Six require clinical/document review; three require engineering integration review. These are mock results, not live AI accuracy evidence. No internet or server is required to read the report. Return feedback by case ID; the page does not submit or save responses. No credentials, environment files, application code, or runtime logs are included.\n'
    class LinkCheck(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key == 'href' and not value.startswith('#'):
                    assert unquote(value) in files, value
    LinkCheck().feed(page)
    destination = QA / 'manual_review_html.zip'
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr('manual_review/' + name, content)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert archive.read('manual_review/index.html').count(b'<section id=') == len(cases)
    print(f'Created {destination}: {len(cases)} review items; {len(files)-2} source/reference files; {destination.stat().st_size:,} bytes. All document links and ZIP integrity verified.')


if __name__ == '__main__':
    main()
