"""Content-verified attachment cache eligibility, stored in existing JSON metadata."""
import hashlib
import json
from src.app.services.document_ingestion import require_parsed
from src.app.services.document_extraction import DocumentProcessingError, DocumentTextExtractor
from src.app.services.summary_outcomes import PIPELINE_VERSION


def attachment_fingerprint(documents, manifest, context, settings):
    if not documents or any(d.extraction_error or not d.content_sha256 for d in documents):
        return None
    from src.app.chains.attachment_summarization.chain import _EXTRACTION_SYSTEM_PROMPT, _SYNTHESIS_SYSTEM_PROMPT
    from src.app.services.clinical_grounding import GROUNDING_POLICY
    from src.app.common.constants.llm import LLM_MODEL
    for document in documents:
        require_parsed(document)
    facts = {'pipeline': PIPELINE_VERSION, 'parser': DocumentTextExtractor.VERSION,
             'manifest': manifest, 'context': context,
             'documents': sorted((d.resource_id or d.file_path, d.content_sha256, d.parsed_text_sha256) for d in documents),
             'prompts': [_EXTRACTION_SYSTEM_PROMPT, _SYNTHESIS_SYSTEM_PROMPT, GROUNDING_POLICY],
             'model': str(LLM_MODEL.GPT_4O_MINI),
             'verification_model': settings.DOCUMENT_VERIFICATION_MODEL,
             'ocr_model': settings.DOCUMENT_OCR_MODEL,
             'ocr_enabled': settings.ENABLE_DOCUMENT_OCR,
             'format_policy': 'fhir-json-xml-multipart-legacy-word-v1'}
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()


async def verified_attachment_cache(repository, request, fingerprint):
    from src.app.services.processing_metrics import record
    if not fingerprint or getattr(request, 'force_regenerate', False):
        record('attachment_cache', 'miss')
        return None
    from src.app.models.conversation_summaries import ConversationSummary
    try:
        row = await repository.get_by_appointment_id_and_source(request.appointment_id, 'attachment_summary')
        if row is None or str(row.user_id) != str(request.user_id):
            record('attachment_cache', 'miss')
            return None
        metadata = row.summary_metadata or {}
        if (metadata.get('source') != 'attachment_summary' or metadata.get('source_fingerprint') != fingerprint
                or metadata.get('processing_outcome') != 'complete' or metadata.get('validation_status') != 'passed'
                or metadata.get('is_clinical_summary') is not True or metadata.get('last_refresh_outcome')):
            record('attachment_cache', 'miss')
            return None
        record('attachment_cache', 'hit')
        return ConversationSummary.model_validate(row)
    except Exception as exc:
        raise DocumentProcessingError('PERSISTENCE_FAILED') from exc
