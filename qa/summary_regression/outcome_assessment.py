"""Separate service utility from observable rejection containment; no case-specific rules."""


def assess_outcomes(observed):
    result = {
        'summary_generation': {'status': 'NOT_ASSESSED', 'reason': 'No summary-path observation.'},
        'safety_containment': {'status': 'NOT_ASSESSED', 'reason': 'No rejected clinical candidate was observed.'},
    }
    if not isinstance(observed, dict):
        return result
    pipeline = observed.get('pipeline_output') or {}
    outcome = observed.get('outcome')
    if 'summary' in pipeline:
        generated = bool(pipeline['summary']) and outcome not in {'unavailable', 'no_documents'}
        result['summary_generation'] = {
            'status': 'PRODUCED' if generated else 'NOT_PRODUCED',
            'reason': 'A candidate summary was returned; consult clinical checks and required review.' if generated else 'No usable clinical summary was returned.',
        }
    if not observed.get('rejected_candidates'):
        return result
    payload = (observed.get('persistence') or {}).get('boundary_payload')
    if not isinstance(payload, dict):
        result['safety_containment']['reason'] = 'A candidate was rejected, but publication-boundary observations are missing.'
        return result
    metadata = payload.get('summaryMetadata') or {}
    clinical_fields = ('keyPoints', 'medications', 'diagnoses', 'instructions', 'recommendations')
    nested_fields = ('procedures_mentioned', 'follow_up')
    data = payload.get('data') or {}
    display = observed.get('display') or {}
    nonclinical = (
        outcome == 'unavailable'
        and pipeline.get('summary') is None
        and metadata.get('is_clinical_summary') is False
        and all(payload.get(key) == [] for key in clinical_fields)
        and all(data.get(key) == [] for key in nested_fields)
        and metadata.get('lab_results') == []
        and metadata.get('risk_factors') == []
        and display.get('kind') == 'unavailable'
        and display.get('template_used') is True
        and bool(display.get('text'))
        and payload.get('summaryText') == display['text']
    )
    if nonclinical:
        result['safety_containment'] = {'status': 'PASS', 'reason': 'Rejected candidate withheld; observed publication payload contains the failure template and empty clinical fields. This checks the in-memory boundary, not a database write.'}
    else:
        result['safety_containment'] = {'status': 'NOT_ASSESSED', 'reason': 'Rejection was observed, but the unavailable/empty-publication checks are not all satisfied. Inspect correction, partial-output or publication evidence.'}
    return result


def classify_contained_result(row, observed):
    """Preserve assertion failures while distinguishing safe unavailability from unsafe output."""
    row['outcome_assessment'] = assess_outcomes(observed)
    row.setdefault('assertion_status', row['status'])
    if row['status'] != 'FAIL' or row['outcome_assessment']['safety_containment']['status'] != 'PASS':
        return
    failures = row.get('failures', [])
    def availability_only(failure):
        check = failure.get('check', {})
        path, op, expected = check.get('path'), check.get('op'), check.get('value')
        actual = failure.get('actual')
        return (
            path == 'pipeline_output.summary' and op == 'present' and expected is True and actual is None
            or path == 'coverage.complete' and op == 'eq' and expected is True and actual is False
            or path == 'outcome' and op == 'eq' and expected == 'complete' and actual == 'unavailable'
        )
    if failures and all(availability_only(failure) for failure in failures):
        row['status'] = 'SAFELY_REJECTED'
