"""Export saved synthetic regression evidence; no model, database, or email calls."""
import hashlib
import html
import json
from pathlib import Path
import shutil
from urllib.parse import quote
import zipfile

QA = Path(__file__).resolve().parents[1]
DEST = QA / 'client_review'
CLINICAL = {'PARSE-06', 'VISION-ROTATED', 'VISION-REVIEW', 'DOCX-TABLE', 'VISION-CROP', 'DOC-LEGACY-VALID'}


def main():
    report = json.loads((QA / 'results/report.json').read_text())
    if report['state'] != 'completed':
        raise RuntimeError('A completed report is required.')
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / 'documents').mkdir(parents=True)
    (DEST / 'observations').mkdir()
    for name, fixture in report['fixtures'].items():
        source = (QA / 'summary_regression' / fixture['path']).resolve()
        target = (DEST / 'documents' / name).resolve()
        if not source.is_relative_to(QA / 'testdata') or not target.is_relative_to(DEST / 'documents'):
            raise ValueError('Invalid fixture path')
        if hashlib.sha256(source.read_bytes()).hexdigest() != fixture['sha256']:
            raise ValueError('Source fixture changed: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    cards = []
    review = ['# Reviewer feedback', '', 'All source files are synthetic. Model summaries and OCR transcriptions in this mock run use controlled responses, not live AI. Do not approve live OCR accuracy from this pack.', '', 'Reviewer: __________ Date: __________', '']
    for row in sorted(report['cases'], key=lambda item: (item['id'] not in CLINICAL, item['status'] != 'REVIEW_REQUIRED', item['id'])):
        artifact = json.loads((QA / 'results' / row['output_file']).read_text()) if row.get('output_file') else {}
        if artifact and artifact.get('run_id') != report['run_id']:
            raise ValueError('Observation belongs to a different run')
        observed = artifact.get('original_observed_output') or {}
        pipeline = observed.get('pipeline_output') or {}
        extraction = observed.get('extraction') or {}
        data = {'case_id': row['id'], 'scenario': row['title'], 'status': row['status'],
                'scope': row['scope'], 'source_documents': row['fixtures'],
                'extracted_text': extraction.get('text'), 'returned_summary': pipeline.get('summary'),
                'displayed_message': observed.get('display'), 'outcome': observed.get('outcome'),
                'error_codes': observed.get('error_codes'), 'expected_and_actual_checks': row.get('checks', []),
                'review_notes': row.get('manual_review', []),
                'control_test_observations': observed.get('regression'),
                'evidence_limit': 'Mock responses test application behavior; they do not establish live AI/OCR accuracy.'}
        filename = row['id'] + '.json'
        (DEST / 'observations' / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        links = ' · '.join(f'<a href="documents/{quote(name, safe="/")}">{html.escape(name)}</a>' for name in row['fixtures']) or 'Control test: no document fixture.'
        def block(value, missing):
            if value is None:
                return '<p>' + html.escape(missing) + '</p>'
            text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
            return '<pre>' + html.escape(text) + '</pre>'
        evidence = block(data['returned_summary'], 'No returned summary recorded. This may be a failure-path or control test; see the displayed outcome and assertions.')
        cards.append(f'<details id="{html.escape(row["id"])}"><summary>{html.escape(row["id"])} — {html.escape(row["title"])} — {row["status"]}</summary><p>{links}</p><p><strong>Evidence: {html.escape(row["scope"])}; mock OCR/model responses are not live accuracy evidence.</strong></p><h3>Extracted text</h3>' + block(data['extracted_text'], 'No extracted-text observation recorded for this case.') + '<h3>Returned summary</h3>' + evidence + '<h3>Displayed message / outcome</h3>' + block(data['displayed_message'], 'No display observation recorded.') + '<h3>Expected versus actual checks</h3>' + block(data['expected_and_actual_checks'], '') + '<h3>Review notes</h3>' + block(data['review_notes'], '') + f'<p><a href="observations/{quote(filename)}">Saved evidence JSON</a></p></details>')
        if row['id'] in CLINICAL:
            review += [f'## {row["id"]}: {row["title"]}', '', f'[Evidence](index.html#{row["id"]})', '',
                       'Compare source versus extracted text and displayed summary: tables, numbers/units, negation, medication status, ordered versus performed, omissions and additions.', '',
                       'Source page/section: __________', 'Discrepancy and expected wording: __________',
                       'Decision: needs change / acceptable mock behavior / insufficient evidence',
                       'Live OCR/model verification: PENDING', '']
    counts = html.escape(json.dumps(report['counts']))
    index = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Synthetic document review</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}details{border:1px solid #ccc;margin:12px 0;padding:12px}summary{cursor:pointer;font-weight:600}.notice{background:#fff0cf;padding:18px}</style><h1>Synthetic document review pack</h1><div class="notice"><strong>MOCK evidence — not live AI accuracy validation.</strong><p>Native parser text is extracted by application code. OCR transcriptions and model summaries use controlled mock responses. Source comparison is useful for reviewing examples and expected behavior; live OCR accuracy remains unverified.</p></div>'
    index += f'<p>Run: {html.escape(report["run_id"])}. {len(report["cases"])} scenarios; {len(report["fixtures"])} synthetic fixtures.</p><p>{counts}</p><p>Six clinical review cases appear first. The other three review items concern access integration and deployed persistence, not clinical document review.</p><p><a href="REVIEW_FEEDBACK.md">Reviewer feedback template</a></p>' + ''.join(cards) + '</html>'
    (DEST / 'index.html').write_text(index)
    (DEST / 'REVIEW_FEEDBACK.md').write_text('\n'.join(review))
    (DEST / 'README.md').write_text('# Client review pack\n\nExtract the ZIP, then open index.html in a browser. Links work locally after extraction. Six clinical review cases appear first; all 494 cases and 114 synthetic fixtures are included. Some fixtures are intentionally malformed, encrypted or unsupported to test failure handling.\n\nThis is saved MOCK evidence. OCR/model responses are controlled test responses, not live generated accuracy evidence. Native parsing results can be inspected against the source. Missing summaries are explicitly identified; no new summaries were generated for this export. Use REVIEW_FEEDBACK.md to record source-specific discrepancies. Live review with representative securely shared documents is still required.\n\nNo application code, environment files, credentials or runtime logs are included. No email was sent. This snapshot is regenerated from the latest completed regression by prepare_client_review.py.\n')
    archive = QA / 'client_review.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(DEST.rglob('*')):
            if path.is_file():
                output.write(path, 'client_review/' + path.relative_to(DEST).as_posix())
    print(f'Created {archive}; {archive.stat().st_size} bytes; {len(cards)} cases, {len(report["fixtures"])} fixtures.')


if __name__ == '__main__':
    main()
