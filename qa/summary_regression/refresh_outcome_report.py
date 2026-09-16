"""Reclassify completed saved observations; no application execution or model calls."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from outcome_assessment import classify_contained_result
from reporting import write_report


def refresh(directory):
    report = json.loads((directory / 'report.json').read_text())
    if report['state'] != 'completed':
        raise RuntimeError('Wait for the active regression to complete before refreshing the report.')
    for row in report['cases']:
        path = (directory / row['output_file']).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('Observed output must be inside the results folder.')
        payload = json.loads(path.read_text())
        if payload['run_id'] != report['run_id'] or payload['case_id'] != row['id'] or payload['scope'] != row['scope']:
            raise ValueError('Saved observation does not belong to this execution.')
        classify_contained_result(row, payload.get('original_observed_output'))
        payload.update(status=row['status'], assertion_status=row['assertion_status'], outcome_assessment=row['outcome_assessment'])
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
        temporary.replace(path)
    counts = Counter(row['status'] for row in report['cases'])
    report['counts'] = {status: counts[status] for status in ('PASS', 'SAFELY_REJECTED', 'FAIL', 'BLOCKED', 'REVIEW_REQUIRED', 'ERROR', 'CANCELLED')}
    for requirement in report.get('requirements', []):
        if requirement.get('status') == 'specified_not_run':
            requirement['status'] = 'specification_only'
    report['presentation_updated_at'] = datetime.now(timezone.utc).isoformat()
    report['presentation_note'] = 'Outcome labels derived from original saved observations; no tests rerun and no expected assertions changed.'
    write_report(directory, report)
    return report['counts']


if __name__ == '__main__':
    print(json.dumps(refresh(Path(__file__).resolve().parents[1] / 'results')))
