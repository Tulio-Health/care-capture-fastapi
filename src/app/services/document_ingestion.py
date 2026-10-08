"""Shared ingestion for attachment and procedure summaries; every input has an outcome."""
import asyncio
import base64
import binascii
from datetime import datetime
from hashlib import sha256
from src.app.common.logging import get_logger
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError

logger = get_logger(__name__)

# Sized by the round9-revision3.md S10 step-4b live-dev runtime measurement, 2026-10-02
# (fastapi-app-v2-dev @ 943f66c, nodejs-app-v2-dev @ ced25e47). This is the REAL BINDING
# cap (attachment-counted, after format-dedup collapses each DocumentReference's
# multi-format representations down to one -- see _select_format_duplicate_skips below).
# fhir_resources.py's repository LIMIT is NOT the cap; it moves together with this
# constant as DOCUMENT_SELECTION_CAP + 1 (a truncation detector, not a second cap -- F7c).
#
# The measurement ran under the SYNC / 110 s regime, not the 300 s async path
# round9-revision3.md expected (fix/async-summary-quickfix is unmerged and not deployed;
# deployed nodeapi sends timeout_seconds: 110), so the >=30% headroom target was <=77 s.
#
# Encounter 97954819 (appointment f5b7474f-2088-4bda-af66-4a47838c4654): 69 documents /
# 5.04 MB ingested in 58.3 s of budget wall clock (budget.job_end wall_seconds=58.311),
# outcome `partial`, validation passed, model_call_headroom=48/64 -- the cap buys back
# extraction time, not model calls. 47% headroom at 69 documents; the same per-document
# cost extrapolated to 100 documents is ~84.5 s = 23% headroom, which FAILS the rule.
# 100 was therefore NOT measured to fit and could not be left in place.
#
# 50 sits below the largest workload measured to fit (69), projecting ~42 s / ~62%
# headroom, deliberately keeping ~2x margin for production documents (larger than dev's
# Cerner-sandbox corpus) and for the slower OCR path (20 of the 69 measured documents).
MAX_DOCUMENTS = 50

# Format preference for attachments that live on the SAME DocumentReference. FHIR's own data
# model already asserts same-DocumentReference attachments are representations of one logical
# document (see care-capture-nodeapi debug report 2026-09-17-document-scope-question), so this
# is a stronger identity signal than the cross-resource checksum dedup below -- no byte/checksum
# comparison needed, just pick the best format and drop the rest.
#
# Rank determined from real prod attachment pairs (Sep 2026), not guessed: the only two format
# combinations observed corpus-wide are html+rtf and pdf+xml. html vs rtf carry IDENTICAL
# clinical content (verified byte-for-byte on real examples) -- rtf's extraction just leaves raw
# pipe-delimited table-cell artifacts (e.g. "|Glucose|206 (H)|70 - 100 mg/dL|") that html's
# extraction renders as clean rows, so html wins on cleanliness. pdf vs xml is decisive: the
# paired `application/xml` attachments observed are Cerner CCL exports whose actual clinical
# narrative is embedded as an UN-DECODED base64 blob (DocumentTextExtractor does not decode it),
# surrounded by ~95% administrative noise (personnel aliases, historical provider names, phone
# numbers) -- the paired pdf has the full human-readable narrative (HISTORY/FINDINGS/IMPRESSION),
# so pdf wins despite xml's much larger raw extracted length.
_FORMAT_PREFERENCE_RANK = {
    "text/html": 0,
    "application/pdf": 1,
    "application/xml": 2,
    "text/rtf": 3,
}
_DEFAULT_FORMAT_RANK = 4


def _select_format_duplicate_skips(attachments) -> set:
    """Within one DocumentReference's attachments list, when 2+ attachments both have
    downloadStatus == "success" they are format-duplicates of the same logical document. Keep
    only the most-preferred format and return the indices of the rest to skip. Attachments that
    aren't successful are left alone -- they still go through their existing failure path
    unchanged, which also means a failed preferred-format attachment never blocks a real
    available duplicate in another format from being processed.
    """
    successful = [
        (index, item.get("contentType"))
        for index, item in enumerate(attachments)
        if isinstance(item, dict) and item.get("downloadStatus") == "success"
    ]
    if len(successful) < 2:
        return set()
    winner_index = min(
        successful,
        key=lambda pair: (_FORMAT_PREFERENCE_RANK.get(pair[1], _DEFAULT_FORMAT_RANK), pair[0]),
    )[0]
    return {index for index, _ in successful if index != winner_index}


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


async def _collect_attachments(references, storage, extractor):
    """Pass A (sequential): walk every reference/attachment making all dedup, limit, and
    metadata decisions in order, so which duplicate is kept and where MAX_DOCUMENTS trips stays
    deterministic. S3-backed attachments are appended to `result` as validated placeholders and
    recorded in `pending`; inline attachments are fully resolved here since their dedup key is a
    post-download content hash and is order-dependent.
    Pass B (concurrent): download + extract every pending S3-backed attachment via
    `asyncio.gather`, bounded by the existing `_DOWNLOAD_POOL` (4) / `_PARSER_SLOTS` (2) -- no
    new semaphore. `_load` mutates each `document` already sitting in `result` in place, so
    `result`'s order never depends on which download finishes first.
    """
    result = []
    # checksum/content_sha256 (both SHA-256 hex of the exact stored bytes) -> ehr_resource_id kept.
    # Scoped to this call, i.e. per-appointment, since callers invoke this once per appointment.
    seen: dict[str, str] = {}
    pending: list[tuple[DocumentAttachment, str]] = []

    async def _load(document: DocumentAttachment, path: str) -> None:
        try:
            content = await storage.download_document(path)
            document.size = len(content)
            document.content_sha256 = sha256(content).hexdigest()
            document.extracted_text = await extractor.extract_text_async(content, document.content_type, document.file_name or path)
            mark_parsed(document)
        except DocumentProcessingError as exc:
            document.extraction_error = exc.code
            document.extraction_error_reason = exc.reason_code  # additive; .code stays canonical
        except Exception:
            document.extraction_error = "INTERNAL_PROCESSING_ERROR"
            document.extraction_error_reason = "INTERNAL_PROCESSING_ERROR"

    for reference in references:
        data = reference.data if isinstance(reference.data, dict) else {}
        attachments = data.get("attachments")
        if not isinstance(attachments, list):
            attachments = [attachments]
        if not attachments:
            attachments = [None]
        # Format-dedup runs first, scoped to this single reference's own attachments, before the
        # cross-reference checksum dedup below -- it narrows a multi-format DocumentReference
        # down to one attachment so the checksum step (and MAX_DOCUMENTS) only ever sees it once.
        format_duplicate_skips = _select_format_duplicate_skips(attachments)
        for index, attachment in enumerate(attachments):
            if index in format_duplicate_skips:
                logger.info(
                    "document_ingestion: skipping format-duplicate attachment within DocumentReference "
                    "resource_id=%s index=%s content_type=%s",
                    reference.ehr_resource_id, index, attachment.get("contentType"),
                )
                continue
            if len(result) >= MAX_DOCUMENTS:
                # F7 (round9-revision3.md S3.3 step 5b / risk R14): construct through
                # DocumentProcessingError so .code is canonicalized the same way every
                # other extraction_error in this module is -- DOCUMENT_LIMIT_EXCEEDED is
                # a RESOURCE_LIMIT_EXCEEDED group MEMBER (document_extraction.py's
                # _ERROR_CODE_GROUPS), not a processing_errors.STAGES key, so writing it
                # as a bare string here (the pre-F7 code) bypassed canonicalization and
                # got coerced to INTERNAL_PROCESSING_ERROR by describe_error -- silently
                # recreating, on the exact path Fix 5 widens, the defect Fix 4 exists to
                # remove. .code is the canonical RESOURCE_LIMIT_EXCEEDED (STAGES key);
                # .reason_code carries the specific DOCUMENT_LIMIT_EXCEEDED on the
                # additive extraction_error_reason sibling, same convention as every
                # other per-document catch site in this function.
                limit_sentinel = DocumentProcessingError("DOCUMENT_LIMIT_EXCEEDED")
                result.append(DocumentAttachment(
                    file_path="unprocessed", content_type="application/octet-stream", extracted_text="",
                    extraction_error=limit_sentinel.code, extraction_error_reason=limit_sentinel.reason_code,
                ))
                # Every already-appended document up to the cap may still have a deferred
                # S3 load pending (Pass B runs at the very end) -- flush it before returning so
                # the cap's own guarantee (everything returned is fully resolved) still holds.
                if pending:
                    await asyncio.gather(*(_load(document, path) for document, path in pending))
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
                    # S3-backed: defer the actual download + extraction to Pass B below, which
                    # runs every pending attachment concurrently. `document` is already fully
                    # validated and in its final `result` position; `_load` fills it in place.
                    result.append(document)
                    pending.append((document, path))
                    continue
                if not isinstance(inline, str) or len(inline) > ((extractor.MAX_FILE_SIZE + 2) // 3) * 4:
                    raise DocumentProcessingError("INVALID_INLINE_CONTENT")
                try:
                    content = base64.b64decode(inline, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise DocumentProcessingError("INVALID_BASE64") from exc
                document.file_path = f"inline://{identity}"
                document.size = len(content)
                document.content_sha256 = sha256(content).hexdigest()
                # Inline base64 attachments carry no vendor checksum field, so fall back to the
                # content hash we just computed ourselves as the dedup key. This stays on the
                # sequential path (unlike S3-backed attachments above) because it hashes bytes
                # after "download" and is order-dependent against the shared `seen` dict.
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
                document.extraction_error_reason = exc.reason_code  # additive; .code stays canonical
            except Exception:
                document.extraction_error = "INTERNAL_PROCESSING_ERROR"
                document.extraction_error_reason = "INTERNAL_PROCESSING_ERROR"
            result.append(document)
    if pending:
        await asyncio.gather(*(_load(document, path) for document, path in pending))
    return result


def drop_parsed_text_duplicates(documents):
    """Drop documents whose normalized parsed text equals another kept document's. The preferred
    one is the best format (same rank table as the within-DocumentReference dedup), ties broken by
    the existing ranked order. Documents without parsed text are never touched."""
    from src.app.services.stub_documents import normalize_text

    groups: dict = {}
    for index, document in enumerate(documents):
        text = getattr(document, "extracted_text", None)
        if getattr(document, "extraction_error", None) or not isinstance(text, str) or not text:
            continue
        groups.setdefault(normalize_text(text), []).append(index)
    drop = set()
    for indexes in groups.values():
        if len(indexes) > 1:
            winner = min(indexes, key=lambda i: (_FORMAT_PREFERENCE_RANK.get(getattr(documents[i], "content_type", None), _DEFAULT_FORMAT_RANK), i))
            drop.update(i for i in indexes if i != winner)
    if drop:
        logger.info("document_ingestion: parsed_text_dedup dropped=%d kept=%d", len(drop), len(documents) - len(drop))
    return [document for index, document in enumerate(documents) if index not in drop]


def split_stub_documents(documents):
    """Return (kept, stub_reasons) -- stub/blank/header-only parsed documents removed."""
    from collections import Counter
    from src.app.services.stub_documents import stub_reason

    kept, reasons = [], Counter()
    for document in documents:
        text = getattr(document, "extracted_text", None)
        reason = None if getattr(document, "extraction_error", None) or not isinstance(text, str) else stub_reason(text)
        if reason:
            reasons[reason] += 1
        else:
            kept.append(document)
    return kept, dict(reasons)


async def process_attachments(references, storage, extractor):
    from src.app.core.settings import get_settings

    result = await _collect_attachments(references, storage, extractor)
    if get_settings().PARSED_TEXT_DEDUP_ENABLED:
        result = drop_parsed_text_duplicates(result)
    return result
