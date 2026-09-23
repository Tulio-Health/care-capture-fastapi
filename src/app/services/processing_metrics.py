"""Bounded, non-PHI event counters; logs can be aggregated by existing monitoring."""
from collections import Counter
import logging
from threading import Lock

_counts = Counter()
_lock = Lock()
_logger = logging.getLogger(__name__)
_STAGES = {'inventory', 'download', 'parsing', 'ocr', 'extraction', 'validation', 'admission', 'orchestration', 'publication', 'persistence', 'internal', 'coverage', 'attachment_cache'}
_OUTCOMES = {'attempt_failure', 'complete', 'partial', 'unavailable', 'no_documents', 'hit', 'miss'}


def record(stage, outcome):
    if stage not in _STAGES or outcome not in _OUTCOMES:
        return
    with _lock:
        _counts[(stage, outcome)] += 1
    _logger.info('document_processing_event stage=%s outcome=%s', stage, outcome)


def snapshot():
    with _lock:
        return {stage + ':' + outcome: count for (stage, outcome), count in _counts.items()}
