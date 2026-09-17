"""Shared ingestion for attachment and procedure summaries; every input has an outcome."""
import base64
import binascii
from datetime import datetime
from hashlib import sha256
from src.app.common.logging import get_logger
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError

logger = get_logger(__name__)

MAX_DOCUMENTS = 100


def safe_string(value, default=None):
    return value if isinstance(value, str) else default


def mark_parsed(document: DocumentAttachment) -> DocumentAttachment:
    document.extracted_text = DocumentTextExtractor.validate_text(document.extracted_text)
    document.parsed_text_sha256 = sha256(document.extracted_text.encode()).hexdigest()
    document.parser_version = DocumentTextExtractor.VERSION
    return document


def require_parsed(document: DocumentAttachment):
    text = DocumentTextExtractor.validate_text(document.extracted_text)
    if document.extraction_error or document.parser_version != DocumentTextExtractor.VERSION or document.parsed_text_sha256 != sha256(text.encode()).hexdigest():
        raise DocumentProcessingError("UNVALIDATED_MODEL_INPUT")


async def process_attachments(references, storage, extractor):
    result = []
    # checksum/content_sha256 (both SHA-256 hex of the exact stored bytes) -> ehr_resource_id kept.
    # Scoped to this call, i.e. per-appointment, since callers invoke this once per appointment.
    seen: dict[str, str] = {}
    for reference in references:
        data = reference.data if isinstance(reference.data, dict) else {}
        attachments = data.get("attachments")
        if not isinstance(attachments, list):
            attachments = [attachments]
        if not attachments:
            attachments = [None]
        for index, attachment in enumerate(attachments):
            if len(result) >= MAX_DOCUMENTS:
                result.append(DocumentAttachment(file_path="unprocessed", content_type="application/octet-stream", extracted_text="", extraction_error="DOCUMENT_LIMIT_EXCEEDED"))
                return result
            item = attachment if isinstance(attachment, dict) else {}
            path = safe_string(item.get("filePath"), "")
            # Pre-download dedup: only trust the vendor checksum when the download actually
            # succeeded (840/840 successful downloads carry a checksum; failed ones never do,
            # and must keep going through their existing DOCUMENT_NOT_READY path unchanged).
            checksum = safe_string(item.get("checksum"), "")
            if checksum and item.get("downloadStatus") == "success":
                kept_resource_id = seen.get(checksum)
                if kept_resource_id is not None:
                    logger.info(
                        "document_ingestion: skipping duplicate attachment content (checksum match) "
                        "kept_resource_id=%s dropped_resource_id=%s checksum=%s",
                        kept_resource_id, reference.ehr_resource_id, checksum,
                    )
                    continue
                seen[checksum] = reference.ehr_resource_id
            identity = sha256(f"{reference.ehr_resource_id}\0{path}\0{index}".encode()).hexdigest()
            document = DocumentAttachment(
                file_path=path or "unavailable", content_type=safe_string(item.get("contentType"), "application/octet-stream"),
                title=safe_string(item.get("title"), safe_string(data.get("type"), "Document")),
                document_type=safe_string(data.get("type")), file_name=safe_string(item.get("fileName")),
                resource_id=identity, extracted_text="",
            )
            try:
                if not isinstance(attachment, dict):
                    raise DocumentProcessingError("INVALID_METADATA")
                inline = item.get("data")
                if not path and inline is None:
                    raise DocumentProcessingError("MISSING_DOCUMENT_PATH")
                if path and item.get("downloadStatus") != "success":
                    raise DocumentProcessingError("DOCUMENT_NOT_READY")
                if data.get("date"):
                    try:
                        document.date = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
                    except (ValueError, TypeError, AttributeError):
                        pass
                if path:
                    content = await storage.download_document(path)
                else:
                    if not isinstance(inline, str) or len(inline) > ((extractor.MAX_FILE_SIZE + 2) // 3) * 4:
                        raise DocumentProcessingError("INVALID_INLINE_CONTENT")
                    try:
                        content = base64.b64decode(inline, validate=True)
                    except (ValueError, binascii.Error) as exc:
                        raise DocumentProcessingError("INVALID_BASE64") from exc
                    document.file_path = f"inline://{identity}"
                document.size = len(content)
                document.content_sha256 = sha256(content).hexdigest()
                if not path:
                    # Inline base64 attachments carry no vendor checksum field, so fall back to
                    # the content hash we just computed ourselves as the dedup key.
                    kept_resource_id = seen.get(document.content_sha256)
                    if kept_resource_id is not None:
                        logger.info(
                            "document_ingestion: skipping duplicate inline attachment (content hash match) "
                            "kept_resource_id=%s dropped_resource_id=%s checksum=%s",
                            kept_resource_id, reference.ehr_resource_id, document.content_sha256,
                        )
                        continue
                    seen[document.content_sha256] = reference.ehr_resource_id
                document.extracted_text = await extractor.extract_text_async(content, document.content_type, document.file_name or path)
                mark_parsed(document)
            except DocumentProcessingError as exc:
                document.extraction_error = exc.code
            except Exception:
                document.extraction_error = "INTERNAL_PROCESSING_ERROR"
            result.append(document)
    return result
