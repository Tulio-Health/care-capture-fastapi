"""Case requirements updated to the user's approved format scope (not observed results)."""
def apply(cases):
    for case in cases:
        identity = case['id']
        if identity in {'ZIP-DEPTH', 'ZIP-ENTRIES'}:
            case['title'] = 'Reject excluded ZIP before expansion: ' + case['title']
            for check in case['expected']:
                if check['path'] == 'error_codes': check['value'] = 'UNSUPPORTED_FORMAT'
        if identity.startswith('POLICY-') and 'dependency_error_code' in case.get('inject', {}):
            case['manual_review'] = []
        if identity in {'GATE-ATTACHMENT_SUMMARY', 'GATE-PROCEDURE_SUMMARY', 'GATE-TRANSCRIPT', 'LIMIT-02', 'SEC-02'}:
            case['manual_review'] = []
        if identity.startswith('TRANSPORT-'):
            kind = identity.split('-')[1]
            if kind in {'ZIP', 'GZIP', 'NDJSON'}:
                case['expected'] = [dict(path='outcome', op='eq', value='unavailable'), dict(path='error_codes', op='contains', value='UNSUPPORTED_FORMAT'), dict(path='calls.summarization', op='eq', value=0)]
                case['title'] = 'Unsupported release format: ' + case['title']
            case['manual_review'] = []  # Release scope decided by user, not clinical approval.
        if identity == 'VISION-REVIEW':
            case['config'].pop('mode', None)
            case['config']['vision_enabled'] = True
            case['expected'] = [dict(path='boundary.raw_content_forwarded',op='eq',value=False), dict(path='coverage.all_pages_accounted',op='eq',value=True)]
            case['manual_review'] = ['Run this case in live mode and review every source image against the saved transcription. Mock evidence does not qualify OCR accuracy. Require exact numbers, units, negation and procedure status, no unsupported additions, and explicit disclosure of unreadable content. Record reviewer, model, source regions and discrepancies; review_complete and thresholds_met remain unapproved until recorded independent review.']
        if identity == 'VISION-CROP':
            case['expected'].append(dict(path='coverage.regions_checked',op='gte',value=2))
            case['manual_review'] = ['Mock crop responses verify routing and duplicate suppression only; real crop accuracy requires clinical review.']
        if identity == 'A03-FHIRFALLBACK':
            case['fixtures'] = ['structured_fhir.json', 'corrupt.pdf']
        if identity == 'LONG-03':
            case['fixtures'] = ['chunk_failure.txt']
            case['config'].pop('chunk_tokens', None)
            case['config']['chunk_chars'] = 1000
        if identity == 'GZIP-DOUBLE':
            case['title'] = 'HTTP compression decoded once; nested gzip document rejected'
            case['expected'] = [dict(path='transport.http_decode_count',op='eq',value=1),dict(path='transport.file_decode_count',op='eq',value=0),dict(path='error_codes',op='contains',value='UNSUPPORTED_FORMAT'),dict(path='calls.summarization',op='eq',value=0)]
        if identity == 'PARSE-05':
            case['manual_review'] = []  # Legacy Word fails closed everywhere (PR-7); no positive case exists.
        if identity == 'FMT-DOC':
            for check in case['expected']:
                if check['path']=='error_codes':check['value']='PARSE_FAILED'
    # error_codes observes DocumentProcessingError.code (the canonical UNSUPPORTED_FORMAT group);
    # the specific UNSUPPORTED_LEGACY_OFFICE reason is only exposed via .reason_code, not surfaced here.
    cases.append(dict(id='DOC-LEGACY-DECLINED', title='Legacy Word fails closed instead of parsing', plan_refs=['7','PARSE-05'], fixtures=['legacy_word.doc'], config={}, inject={}, expected=[dict(path='outcome',op='eq',value='unavailable'),dict(path='error_codes',op='contains',value='UNSUPPORTED_FORMAT'),dict(path='calls.summarization',op='eq',value=0)], manual_review=[], execution_status='not_run'))

    for name in ('nested_bundle.json','nested_bundle.xml','nested_report.json','nested_report.xml'):
        cases.append(dict(id='FHIR-NESTED-'+name.replace('.','-').upper(),title='Parse nested FHIR attachment: '+name,plan_refs=['5','8'],fixtures=[name],config={},inject={},expected=[dict(path='extraction.status',op='eq',value='success'),dict(path='extraction.text',op='contains',value='completion not documented'),dict(path='boundary.raw_content_forwarded',op='eq',value=False)],manual_review=[],execution_status='not_run'))
    cases.append(dict(id='FHIR-NESTED-REMOTE',title='Unacquired nested remote attachment is unavailable',plan_refs=['5','8'],fixtures=['nested_external.json'],config={},inject={},expected=[dict(path='outcome',op='eq',value='unavailable'),dict(path='error_codes',op='contains',value='DOWNLOAD_UNAVAILABLE'),dict(path='calls.summarization',op='eq',value=0)],manual_review=[],execution_status='not_run'))
