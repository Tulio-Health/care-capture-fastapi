"""Shared ingestion for attachment and procedure summaries; every input has an outcome."""
import base64
import binascii
from datetime import datetime
from hashlib import sha256
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError

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
                document.extracted_text = await extractor.extract_text_async(content, document.content_type, document.file_name or path)
                mark_parsed(document)
            except DocumentProcessingError as exc:
                document.extraction_error = exc.code
            except Exception:
                document.extraction_error = "INTERNAL_PROCESSING_ERROR"
            result.append(document)
    return result
