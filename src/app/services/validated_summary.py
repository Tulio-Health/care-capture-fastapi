"""In-process integrity seal between clinical validation and JSON publication."""
import hashlib
import json
from src.app.services.document_extraction import DocumentProcessingError


def _digest(summary):
    return hashlib.sha256(json.dumps(summary.model_dump(mode='json'), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def seal_summary(summary):
    summary._validation_digest = _digest(summary)
    return summary


def require_validated_summary(summary):
    if not getattr(summary, '_validation_digest', None) or summary._validation_digest != _digest(summary):
        raise DocumentProcessingError('CLINICAL_EVIDENCE_FAILED')
