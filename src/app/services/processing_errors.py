"""Public, nonclinical error taxonomy; never serialize dependency exception messages."""
STAGES = {
    'SOURCE_INVENTORY_FAILED': ('inventory', True),
    'DOCUMENT_NOT_FOUND': ('download', False),
    'DOCUMENT_ACCESS_DENIED': ('download', False),
    'DOWNLOAD_PENDING': ('download', False),
    'DOWNLOAD_TIMEOUT': ('download', True),
    'DOWNLOAD_UNAVAILABLE': ('download', True),
    'EMPTY_FILE': ('parsing', False),
    'FILE_TOO_LARGE': ('parsing', False),
    'UNSUPPORTED_FORMAT': ('parsing', False),
    'ENCODING_UNRESOLVED': ('parsing', False),
    'FORMAT_CONFLICT': ('parsing', False),
    'PARSE_FAILED': ('parsing', False),
    'PASSWORD_PROTECTED': ('parsing', False),
    'NO_READABLE_TEXT': ('parsing', False),
    'OCR_REQUIRED': ('ocr', False),
    'OCR_TIMEOUT': ('ocr', True),
    'EXTRACTION_QUALITY_FAILED': ('parsing', False),
    'MODEL_TIMEOUT': ('extraction', True),
    'MODEL_RATE_LIMITED': ('extraction', True),
    'MODEL_AUTH_FAILED': ('extraction', False),
    'MODEL_UNAVAILABLE': ('extraction', True),
    'MODEL_OUTPUT_INVALID': ('extraction', False),
    'CLINICAL_EVIDENCE_FAILED': ('validation', False),
    'RESOURCE_LIMIT_EXCEEDED': ('admission', False),
    'SUMMARY_DEADLINE_EXCEEDED': ('orchestration', True),
    'SOURCE_VERSION_CHANGED': ('publication', True),
    'SOURCE_MANIFEST_CHANGED': ('publication', True),
    'PERSISTENCE_FAILED': ('persistence', False),
    'INVALID_PERSISTENCE_PAYLOAD': ('persistence', False),
    'PERSISTENCE_PAYLOAD_TOO_LARGE': ('persistence', False),
    'INTERNAL_PROCESSING_ERROR': ('internal', False),
}


def describe_error(code, source_id=None):
    code = code if code in STAGES else 'INTERNAL_PROCESSING_ERROR'
    stage, retryable = STAGES[code]
    result = {'error': code, 'stage': stage, 'transient_retryable': retryable}
    if isinstance(source_id, str):
        result['source_id'] = source_id[:256]
    return result
