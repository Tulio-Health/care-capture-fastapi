"""Unit test for Fix 4 (round9-revision3.md Sec 3.4): when every document passed to
`AttachmentSummarizationChain.analyze` already failed extraction individually, `_create_batches`
returns no batches. Prior behavior raised a bare `ValueError`, which the generic
`except Exception` catch site in `attachment_summarization.py` could not distinguish from any
other chain failure -- mislabeling it `INTERNAL_PROCESSING_ERROR` and double-counting documents
already counted under EXTRACTION_QUALITY_FAILED/OCR_*. Fixed: raises the typed
`DocumentProcessingError("NO_DOCUMENTS")` -- the existing producer-side name for this exact
concept (see `fhir_analysis.py`'s own `NO_DOCUMENTS` raise/check for the same state).
"""
import pytest

from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.document_extraction import DocumentProcessingError


def _failed_doc(resource_id, extraction_error):
    return DocumentAttachment(
        file_path=f"s3://bucket/{resource_id}.txt",
        content_type="text/plain",
        resource_id=resource_id,
        extracted_text="",
        extraction_error=extraction_error,
    )


@pytest.mark.asyncio
async def test_all_documents_already_failed_raises_typed_no_documents_not_bare_value_error():
    documents = [
        _failed_doc("doc-1", "EXTRACTION_QUALITY_FAILED"),
        _failed_doc("doc-2", "OCR_UNREADABLE"),
    ]
    chain = AttachmentSummarizationChain()

    with pytest.raises(DocumentProcessingError) as exc_info:
        await chain.analyze({"appointment_date": "2026-01-01", "purpose": "Follow-up"}, documents)

    # Name corrected to NO_DOCUMENTS per round-5 rt2-no-valid-documents-duplicates-existing-code:
    # fhir_analysis.py already establishes this as the producer-side name for the same concept.
    assert exc_info.value.reason_code == "NO_DOCUMENTS"
    # Registered in neither _ERROR_CODE_GROUPS nor STAGES, so .code passes through verbatim --
    # this is what lets the attachment_summarization.py catch site branch on it before it would
    # otherwise reach processing_errors.py's INTERNAL_PROCESSING_ERROR coercion.
    assert exc_info.value.code == "NO_DOCUMENTS"
