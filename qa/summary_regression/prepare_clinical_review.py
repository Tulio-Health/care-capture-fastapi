"""Prepare a reviewer packet from saved synthetic observations; never calls AI or a DB."""
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / 'results/report.json').read_text())
    if report['state'] != 'completed':
        raise RuntimeError('Complete the regression before preparing clinical review.')
    lines = ['# Clinical review packet', '', f"Source regression: `{report['run_id']}`. Review status: **PENDING**.", '',
             'All documents are synthetic. No clinical approval is implied by automated checks or by this packet.', '',
             'Reviewer name/role: __________  Review date: __________', '',
             'For each case check transcription, table relationships, numbers/units, negation, medication status, procedure ordered versus performed, missing facts, and patient/source attribution. Record discrepancies using source page/section and output field. Do not infer undocumented clinical meaning.', '',
             'Mock outputs establish application behavior only; they cannot establish OCR or model accuracy. Rejected candidates below were withheld from the user. Review the extracted text separately from the rejection decision.', '',
             'This packet snapshots the saved text observations. Document and detailed-output links refer to the current QA files and may change after another regression; regenerate this packet before each review.', '',
             '[Full regression report](results/report.html)', '']
    selected = []
    for row in report['cases']:
        notes = ' '.join(row.get('manual_review', [])).lower()
        if row['scope'] == 'application_live' or any(term in notes for term in ('transcription', 'table associations', 'header/value/unit', 'clinical review')):
            selected.append(row)
    for row in selected:
        artifact = json.loads((ROOT / 'results' / row['output_file']).read_text())
        if artifact['run_id'] != report['run_id']:
            raise ValueError('Mismatched saved observation')
        observed = artifact.get('original_observed_output') or {}
        pipeline = observed.get('pipeline_output') or {}
        lines += [f"## {row['id']} — {row['title']}", '', f"Execution: `{row['scope']}`. Result: `{row['status']}`.", '']
        lines += [f"- [Source: {name}](testdata/{quote(name)})" for name in row['fixtures']]
        lines += ['', f"[Full observed output](results/{quote(row['output_file'], safe='/')})", '',
                  'Required review: ' + (' '.join(row.get('manual_review', [])) or 'Compare source evidence with extracted and returned content.'), '',
                  '### Automated expectations and observations', '', '```json', json.dumps(row.get('checks', []), indent=2, ensure_ascii=False), '```', '',
                  '### Actual extracted text', '', '```text', (observed.get('extraction') or {}).get('text') or 'No extracted-text observation available; this case needs execution evidence.', '```', '',
                  '### Actual returned summary / user message', '', '```json', json.dumps({'summary': pipeline.get('summary'), 'display': observed.get('display'), 'outcome_assessment': row.get('outcome_assessment')}, indent=2, ensure_ascii=False), '```', '',
                  '### Rejected candidates — NOT published', '', '```json', json.dumps({'candidates': observed.get('rejected_candidates', []), 'validation_issues': observed.get('validation_issues', [])}, indent=2, ensure_ascii=False), '```', '',
                  '- [ ] Source-to-text accuracy checked (including tables, numbers and units).',
                  '- [ ] Returned content contains only supported facts and correct statuses.',
                  '- [ ] Missing content and any safe rejection were assessed.',
                  '- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.', '',
                  'Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE', '',
                  'Discrepancies, source references and reviewer rationale: ____________________', '']
    (ROOT / 'CLINICAL_REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Prepared {len(selected)} review entries in qa/CLINICAL_REVIEW.md; all remain pending.')


if __name__ == '__main__':
    main()
