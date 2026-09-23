"""Fail-closed document extraction. No raw-document fallback is permitted."""
from __future__ import annotations

import asyncio
import codecs
import csv
import hashlib
import io
import json
import mimetypes
import re
import zipfile
import xml.etree.ElementTree as ET
from email.message import Message
from html.parser import HTMLParser
from typing import Optional


class DocumentProcessingError(ValueError):
    """Stable, non-PHI error code suitable for persisted processing metadata."""
    def __init__(self, code: str):
        groups = {
            "ENCODING_UNRESOLVED": {"UNSUPPORTED_ENCODING", "INVALID_ENCODING", "CONFLICTING_ENCODING"},
            "FORMAT_CONFLICT": {"INVALID_MIME", "MIME_MISMATCH"},
            "NO_READABLE_TEXT": {"EMPTY_TEXT"},
            "PASSWORD_PROTECTED": {"ENCRYPTED_DOCUMENT"},
            "UNSUPPORTED_FORMAT": {"UNSUPPORTED_LEGACY_OFFICE", "UNSUPPORTED_ARCHIVE", "UNSUPPORTED_EMBEDDED_CONTENT", "UNSUPPORTED_IMAGE", "PARSER_UNAVAILABLE", "UNSUPPORTED_TRACKED_CHANGES", "ENCODED_DOCUMENT_REQUIRES_TRANSPORT_DECODING"},
            "OCR_REQUIRED": {"OCR_DISABLED"},
            "PARSE_FAILED": {"MALFORMED_RTF", "UNSAFE_XML", "UNSAFE_ARCHIVE", "INVALID_COMPRESSION", "PARSER_PROCESS_FAILED", "PARSER_TIMEOUT", "RENDER_FAILED"},
            "EXTRACTION_QUALITY_FAILED": {"INVALID_TEXT", "UNPARSED_CONTENT", "UNVALIDATED_MODEL_INPUT", "NON_CLINICAL_ERROR_DOCUMENT", "OCR_UNREADABLE", "OCR_VERIFICATION_FAILED", "OCR_INVALID_OUTPUT"},
            "RESOURCE_LIMIT_EXCEEDED": {"TEXT_LIMIT_EXCEEDED", "PAGE_LIMIT_EXCEEDED", "ARCHIVE_LIMIT_EXCEEDED", "IMAGE_PIXEL_LIMIT_EXCEEDED", "OCR_PAGE_LIMIT_EXCEEDED", "OCR_RENDER_LIMIT_EXCEEDED", "OCR_VISION_CALL_LIMIT_EXCEEDED", "COMPRESSION_LIMIT_EXCEEDED", "DOCUMENT_LIMIT_EXCEEDED", "CHUNK_LIMIT_EXCEEDED", "SYNTHESIS_BUDGET_EXCEEDED", "SYNTHESIS_RECORD_LIMIT_EXCEEDED", "PROCEDURE_CONTEXT_LIMIT_EXCEEDED", "TRANSCRIPT_CONTEXT_LIMIT_EXCEEDED", "FHIR_CONTEXT_LIMIT_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED", "VALIDATION_BUDGET_EXCEEDED", "SUMMARY_BUSY", "DOWNLOAD_BUSY"},
            "MODEL_OUTPUT_INVALID": {"MODEL_SOURCE_RECONCILIATION_FAILED", "OCR_INCOMPLETE_RESPONSE", "CLASSIFICATION_ID_MISMATCH"},
            # PR-11 (N-6): GROUNDING_VALIDATION_FAILED intentionally canonicalizes to
            # CLINICAL_EVIDENCE_FAILED here, NOT its own top-level code. chain.py's
            # _extract_batch/_synthesize_records grant exactly one repair attempt keyed off
            # `exc.code in {"CLINICAL_EVIDENCE_FAILED", "MODEL_OUTPUT_INVALID"}`; splitting this
            # code out would silently drop it from that retry set (and from every other
            # CLINICAL_EVIDENCE_FAILED-keyed check) unless every one of those sites were updated
            # too -- not worth the risk for a log-triage label. The specific reason is not lost:
            # it survives on `.reason_code` (see __init__ below), which routes/care_capture.py
            # already reads independently of `.code` for HTTP status mapping. Log/triage code
            # that wants the specific code should read `.reason_code`, not `.code`.
            "CLINICAL_EVIDENCE_FAILED": {"GROUNDING_VALIDATION_FAILED", "INVALID_SOURCE_EVIDENCE", "DIAGNOSIS_WORDING_NOT_GROUNDED", "PROCEDURE_STATUS_NOT_GROUNDED"},
            "DOWNLOAD_PENDING": {"DOCUMENT_NOT_READY"},
            "DOWNLOAD_UNAVAILABLE": {"MISSING_DOCUMENT_PATH"},
            "INTERNAL_PROCESSING_ERROR": {"INVALID_METADATA", "INVALID_CONTENT", "INVALID_INLINE_CONTENT", "INVALID_BASE64", "DOCUMENT_PROCESSING_FAILED"},
        }
        self.reason_code = code
        self.code = next((canonical for canonical, members in groups.items() if code in members), code)
        super().__init__(self.code)
        from src.app.services.processing_errors import STAGES
        from src.app.services.processing_metrics import record
        record(STAGES.get(self.code, ("internal", False))[0], "attempt_failure")


# Presentation/plumbing attributes with no clinical signal. Clinical values
# (displayName, value, unit, code, statusCode, ...) are deliberately NOT here:
# a CDA can carry the only diagnosis/value/unit in an attribute (see the
# comment above walk() in _xml_text).
#
# moodCode/negationInd/typeCode/inversionInd are deliberately NOT here either
# (fixed 2026-09-22, see .claude/debug-reports/2026-09-22-async-summarization-fix/
# xml-compression-information-loss-audit.md §9.1 in care-capture-nodeapi): they
# were previously dropped as "plumbing", but moodCode distinguishes an EVN
# (actually happened) entry from INT/RQO/PRP/ARQ (ordered/planned, NOT done) -
# the CDA-native form of this codebase's "ordered vs performed" bug - and
# negationInd="true" means the finding did NOT occur. They never appear as raw
# key=value noise (see _XML_SEMANTIC_ATTRS below); walk() renders them as an
# explicit prefix on the entry's line only when they carry real signal.
_XML_NOISE_ATTRS = {"styleCode", "ID", "width", "span", "root", "extension",
                    "codeSystem", "codeSystemName", "classCode",
                    "contextControlCode",
                    "independentInd", "determinerCode", "type"}
# Attributes suppressed from the raw key=value dump like _XML_NOISE_ATTRS, but
# with a semantic prefix rendered on the entry's line when they carry signal -
# see walk() in _xml_text.
_XML_SEMANTIC_ATTRS = {"moodCode", "negationInd", "typeCode", "inversionInd"}
_XML_MOOD_PREFIXES = {"INT": "[ORDERED/PLANNED]", "RQO": "[ORDERED/PLANNED]",
                      "PRP": "[ORDERED/PLANNED]", "ARQ": "[ORDERED/PLANNED]",
                      "APT": "[APPOINTMENT]", "GOL": "[GOAL]"}
# Only meaningful on <entryRelationship> - e.g. the link from an allergy to its
# reaction (MFST) or from a finding to its cause (CAUS)/reason (RSON). Other
# typeCode values (COMP, REFR, SUBJ, ...) and inversionInd stay suppressed.
_XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES = {"MFST": "MANIFESTATION:", "RSON": "REASON:", "CAUS": "CAUSE:"}
# Elements that are pure CDA plumbing - never clinical content.
_XML_NOISE_TAGS = {"templateId", "id", "realmCode", "typeId", "setId",
                   "versionNumber", "confidentialityCode", "languageCode"}
# Redundancy-only compression of the non-narrative _xml_text walk (design:
# care-capture-nodeapi .claude/debug-reports/2026-09-22-async-summarization-fix/
# cda-redundancy-compression-design.md). Both are layout/verbosity knobs only;
# correctness (Invariant R) does not depend on either value.
_XML_GROUP_MAX_PARTS = 40  # highest node emitting <= this many parts becomes one "@" group
_XML_BLOCK_MIN_PARTS = 6   # byte-identical subtrees emitting >= this many parts back-reference


class DocumentTextExtractor:
    MAX_FILE_SIZE = 50 * 1024 * 1024
    MAX_TEXT_CHARS = 1_000_000
    MAX_PAGES = 300
    MAX_ZIP_ENTRIES = 2000
    MAX_ARCHIVE_EXPANDED_BYTES = 50 * 1024 * 1024
    RTF_MAGIC = b"{\\rtf"
    VERSION = "strict-5"
    MAX_ARCHIVE_DEPTH = 2

    def __init__(self, *, disabled_adapters=(), transport_enabled=True, allow_containers=True):
        self.disabled_adapters = frozenset(disabled_adapters)
        self.last_adapter = None
        self.declared_mime = None
        self.detected_mime = None
        self.transport_enabled = transport_enabled
        self.allow_containers = allow_containers
        self.decode_count = 0
        self._transport_depth = 0
        self._expanded_bytes = 0
        self._embedded_attachments = 0
        self._work_directory = None

    ALIASES = {
        "application/x-rtf": "application/rtf", "text/rtf": "application/rtf",
        "text/richtext": "application/rtf", "application/x-pdf": "application/pdf",
        "text/xml": "application/xml", "application/cda+xml": "application/xml",
        "application/hl7-v3+xml": "application/xml", "application/xhtml+xml": "text/html",
        "text/json": "application/json", "application/fhir+json": "application/json",
        "application/fhir+xml": "application/xml", "image/jpg": "image/jpeg",
        "image/x-tiff": "image/tiff",
    }

    @classmethod
    def normalize_mime(cls, value: str | None) -> tuple[str, str | None]:
        if value is not None and not isinstance(value, str):
            raise DocumentProcessingError("INVALID_METADATA")
        value = value or "application/octet-stream"
        if "\r" in value or "\n" in value or len(value) > 1024:
            raise DocumentProcessingError("INVALID_MIME")
        if len(re.findall(r'(?<!\\)"', value)) % 2:
            raise DocumentProcessingError("INVALID_MIME")
        message = Message()
        message["content-type"] = value
        base = value.split(";", 1)[0].strip().lower()
        if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", base):
            raise DocumentProcessingError("INVALID_MIME")
        charsets = [str(v).strip() for k, v in message.get_params()[1:] if k.lower() == "charset"]
        try:
            names = {codecs.lookup(c).name for c in charsets}
        except LookupError as exc:
            raise DocumentProcessingError("UNSUPPORTED_ENCODING") from exc
        if len(names) > 1:
            raise DocumentProcessingError("INVALID_MIME")
        return cls.ALIASES.get(base, base), next(iter(names), None)

    @staticmethod
    def _decode(content: bytes, charset: str | None = None) -> str:
        bom = None
        for marker, encoding in ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                                 (codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"),
                                 (codecs.BOM_UTF16_BE, "utf-16")):
            if content.startswith(marker):
                bom = encoding
                break
        if bom and charset and not charset.replace("-", "").startswith(bom.replace("-", "").split("sig")[0]):
            raise DocumentProcessingError("CONFLICTING_ENCODING")
        if charset in {"utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"}:
            opposite = {
                "utf-16-le": codecs.BOM_UTF16_BE, "utf-16-be": codecs.BOM_UTF16_LE,
                "utf-32-le": codecs.BOM_UTF32_BE, "utf-32-be": codecs.BOM_UTF32_LE,
            }[charset]
            if content.startswith(opposite):
                raise DocumentProcessingError("CONFLICTING_ENCODING")
        encoding = bom or charset or "utf-8"
        # Reject codecs that are not character encodings (e.g. unicode_escape).
        if not re.fullmatch(r"(?:utf[-_]?\d+(?:[-_](?:le|be|sig))?|ascii|iso8859-\d+|cp\d+|shift_jis|euc_jp|gb18030|gbk|big5|koi8-r)", encoding):
            raise DocumentProcessingError("UNSUPPORTED_ENCODING")
        try:
            return content.decode(encoding, errors="strict")
        except (UnicodeError, LookupError) as exc:
            raise DocumentProcessingError("INVALID_ENCODING") from exc

    @classmethod
    def validate_text(cls, text: str) -> str:
        if not text or not text.strip():
            raise DocumentProcessingError("EMPTY_TEXT")
        if len(text) > cls.MAX_TEXT_CHARS:
            raise DocumentProcessingError("TEXT_LIMIT_EXCEEDED")
        if "\ufffd" in text or any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise DocumentProcessingError("INVALID_TEXT")
        if text.lstrip("\ufeff \t\r\n").startswith(("{\\rtf", "%PDF-")):
            raise DocumentProcessingError("UNPARSED_CONTENT")
        if re.search(r"</?(?:html|body|head|script|ClinicalDocument|DocumentReference|Binary)\b|<\?xml", text, re.I):
            raise DocumentProcessingError("UNPARSED_CONTENT")
        return text.strip()

    def extract_text(self, content: bytes, content_type: str, file_name: Optional[str] = None) -> str:
        if not isinstance(content, bytes):
            raise DocumentProcessingError("INVALID_CONTENT")
        if not content:
            raise DocumentProcessingError("EMPTY_FILE")
        if len(content) > self.MAX_FILE_SIZE:
            raise DocumentProcessingError("FILE_TOO_LARGE")
        mime, charset = self.normalize_mime(content_type)
        self.declared_mime = content_type
        # Release format policy is internal: compressed document containers are unsupported.
        # HTTP Content-Encoding is decoded separately by the download transport.
        if content.startswith(b"\x1f\x8b") or mime in {"application/gzip", "application/x-gzip", "application/zip", "application/fhir+ndjson", "application/x-ndjson", "application/ndjson"}:
            raise DocumentProcessingError("UNSUPPORTED_FORMAT")
        head = content.removeprefix(codecs.BOM_UTF8).lstrip()
        detected = None
        if head.startswith(self.RTF_MAGIC):
            detected = "application/rtf"
        elif head.startswith(b"%PDF-"):
            detected = "application/pdf"
        elif content.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = archive.namelist()
                    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                        raise DocumentProcessingError("UNSUPPORTED_ARCHIVE")
                    else:
                        detected = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            except zipfile.BadZipFile as exc:
                raise DocumentProcessingError("PARSE_FAILED") from exc
        elif content.startswith((b"\x89PNG", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"GIF8")) or (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
            kind = "png" if content.startswith(b"\x89PNG") else "jpeg" if content.startswith(b"\xff\xd8") else "tiff" if content.startswith((b"II*", b"MM\x00*")) else "gif" if content.startswith(b"GIF8") else "webp"
            if kind in self.disabled_adapters or (kind == "gif" and "animated" in self.disabled_adapters):
                raise DocumentProcessingError("UNSUPPORTED_FORMAT")
            self.last_adapter = "vision"
            raise DocumentProcessingError("OCR_REQUIRED")
        elif content.startswith(b"\xd0\xcf\x11\xe0"):
            detected = "application/msword"
        # Signature takes precedence over unreliable connector metadata, never vice versa.
        mime = detected or mime
        if mime.endswith("+xml"):
            mime = "application/xml"
        elif mime.endswith("+json"):
            mime = "application/json"
        if mime == "application/octet-stream" and file_name:
            mime = self._infer_type_from_filename(file_name)
        if mime == "application/octet-stream":
            raw = self._decode(content, charset)
            stripped = raw.lstrip()
            if re.match(r"(?:<\?xml[^>]*>\s*)?<(?:!doctype\s+html|html\b)", stripped, re.I):
                mime = "text/html"
            elif stripped.startswith("<"):
                mime = "application/xml"
            elif stripped.startswith(("{", "[")):
                mime = "application/json"
            else:
                # A strict text adapter is still a parser: binary/control bytes and
                # opaque encoded payloads never become clinical model input.
                self.validate_text(raw)
                if re.fullmatch(r"[A-Za-z0-9+/=\s]{80,}", raw) and not re.search(r"[ .,:;!?]", raw):
                    raise DocumentProcessingError("UNSUPPORTED_FORMAT")
                mime = "text/plain"
        self.detected_mime = mime
        if mime in {"application/zip", "application/json", "application/xml", "application/fhir+ndjson", "application/x-ndjson"} or mime.startswith("multipart/"):
            from src.app.services.document_transport import extract_transport
            try:
                transported = extract_transport(self, content, mime, charset, content_type, file_name)
            except DocumentProcessingError:
                raise
            except Exception as exc:
                raise DocumentProcessingError("PARSE_FAILED") from exc
            if transported is not None:
                return transported
        adapter = {"application/msword": "doc", "application/pdf": "pdf", "application/rtf": "rtf", "application/xml": "xml", "text/html": "html", "application/json": "json", "text/csv": "csv", "text/tab-separated-values": "csv", "text/plain": "text", "text/markdown": "text", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}.get(mime)
        if adapter in self.disabled_adapters or (content_type and content_type.split(';')[0].strip().lower() == "text/richtext" and "richtext" in self.disabled_adapters):
            raise DocumentProcessingError("UNSUPPORTED_FORMAT")
        self.last_adapter = adapter
        try:
            if mime == "application/pdf":
                if not head.startswith(b"%PDF-"):
                    raise DocumentProcessingError("MIME_MISMATCH")
                text = self._extract_from_pdf(content)
            elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                text = self._extract_from_docx(content)
            elif mime == "application/msword":
                from src.app.services.legacy_word import extract_legacy_word
                text = extract_legacy_word(self, content)
            elif mime == "application/rtf":
                text = self._extract_from_rtf(content, charset=charset)
            elif mime == "application/xml":
                raw = self._decode(content, charset) if charset else content
                text = self._xml_text(raw)
            elif mime == "text/html":
                text = self._html_text(self._decode(content, charset))
            elif mime in {"application/json", "text/csv", "text/tab-separated-values", "text/plain", "text/markdown"}:
                raw = self._decode(content, charset)
                if mime == "application/json":
                    parsed = json.loads(raw)
                    def reject_embedded_documents(value):
                        if isinstance(value, dict):
                            if value.get("resourceType") in {"Binary", "DocumentReference", "Media"}:
                                raise DocumentProcessingError("ENCODED_DOCUMENT_REQUIRES_TRANSPORT_DECODING")
                            for child in value.values():
                                reject_embedded_documents(child)
                        elif isinstance(value, list):
                            for child in value:
                                reject_embedded_documents(child)
                    reject_embedded_documents(parsed)
                    def parse_nested_text(value, field_name=""):
                        if isinstance(value, dict):
                            if ("data" in value or "url" in value) and ("contentType" in value or field_name in {"attachment", "presentedForm"} or field_name.endswith("Attachment")):
                                from src.app.services.document_transport import parse_embedded_attachment
                                parsed_text = parse_embedded_attachment(self, value)
                                return {**{key: parse_nested_text(child) for key, child in value.items() if key not in {"data", "url"}}, "parsed_attachment_text": parsed_text}
                            return {key: parse_nested_text(child, key) for key, child in value.items()}
                        if isinstance(value, list):
                            return [parse_nested_text(child, field_name) for child in value]
                        if isinstance(value, str):
                            if value.lstrip().startswith("{\\rtf"):
                                return self.validate_text(self._extract_from_rtf(value.encode("utf-8"), charset="utf-8"))
                            if re.search(r"<(?:[A-Za-z][A-Za-z0-9:_-]*)(?:\s[^>]*)?>", value):
                                return self.validate_text(self._html_text(value))
                            if value.lstrip().startswith(("%PDF-", "data:")):
                                raise DocumentProcessingError("UNSUPPORTED_EMBEDDED_CONTENT")
                            if value.strip():
                                self.validate_text(value)
                        return value
                    parsed = parse_nested_text(parsed)
                    text = json.dumps(parsed, ensure_ascii=False, indent=2)
                elif mime in {"text/csv", "text/tab-separated-values"}:
                    rows = csv.reader(io.StringIO(raw), delimiter="\t" if mime.endswith("tab-separated-values") else ",", strict=True)
                    text = "\n".join(" | ".join(row) for row in rows)
                else:
                    if re.search(r"<(?:[A-Za-z][A-Za-z0-9:_-]*)(?:\s[^>]*)?>", raw):
                        raise DocumentProcessingError("MIME_MISMATCH")
                    text = raw
            elif mime.startswith("image/"):
                if mime not in {"image/png", "image/jpeg", "image/tiff", "image/webp", "image/gif", "image/bmp"}:
                    raise DocumentProcessingError("UNSUPPORTED_FORMAT")
                if mime.split("/", 1)[1] in self.disabled_adapters:
                    raise DocumentProcessingError("UNSUPPORTED_FORMAT")
                self.last_adapter = "vision"
                raise DocumentProcessingError("OCR_REQUIRED")
            else:
                raise DocumentProcessingError("UNSUPPORTED_FORMAT")
            return self.validate_text(text)
        except DocumentProcessingError:
            raise
        except ImportError as exc:
            raise DocumentProcessingError("PARSER_UNAVAILABLE") from exc
        except Exception as exc:
            raise DocumentProcessingError("PARSE_FAILED") from exc

    def _extract_from_pdf(self, content: bytes, file_name=None) -> str:
        import fitz
        with fitz.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise DocumentProcessingError("ENCRYPTED_DOCUMENT")
            if len(doc) > self.MAX_PAGES:
                raise DocumentProcessingError("PAGE_LIMIT_EXCEEDED")
            parts = []
            for page in doc:
                text = page.get_text(sort=True)
                from src.app.services.document_image_routing import pdf_page_requires_ocr
                if pdf_page_requires_ocr(page, text):
                    raise DocumentProcessingError("OCR_REQUIRED")
                if text.strip():
                    parts.append(f"[Page {page.number + 1}]\n{text}")
            return "\n\n".join(parts)

    def _extract_from_docx(self, content: bytes, file_name=None) -> str:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > self.MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > self.MAX_ARCHIVE_EXPANDED_BYTES:
                raise DocumentProcessingError("ARCHIVE_LIMIT_EXCEEDED")
            if any(i.flag_bits & 1 or ".." in i.filename.split("/") or i.filename.startswith("/") for i in infos):
                raise DocumentProcessingError("UNSAFE_ARCHIVE")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise DocumentProcessingError("UNSAFE_ARCHIVE")
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise DocumentProcessingError("UNSUPPORTED_ARCHIVE")
            if any("vbaProject" in n or n.startswith("word/embeddings/") for n in names):
                raise DocumentProcessingError("UNSUPPORTED_EMBEDDED_CONTENT")
            parts = []
            for name in names:
                if name == "word/document.xml" or re.fullmatch(r"word/(?:header\d*|footer\d*|footnotes|endnotes)\.xml", name):
                    raw = archive.read(name)
                    text = self._word_text(raw)
                    from src.app.services.document_image_routing import docx_has_unsupported_images
                    if docx_has_unsupported_images(ET.fromstring(raw), marginal_part=bool(re.fullmatch(r"word/(?:header\d*|footer\d*)\.xml", name))):
                        raise DocumentProcessingError("UNSUPPORTED_EMBEDDED_CONTENT")
                    parts.append(text)
            return "\n".join(parts)

    @staticmethod
    def _word_text(content):
        # Validate XML safety before interpreting Word structure.
        DocumentTextExtractor._xml_text(content)
        root = ET.fromstring(content)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        if any(element.tag in {namespace + "del", namespace + "ins"} for element in root.iter()):
            raise DocumentProcessingError("UNSUPPORTED_TRACKED_CHANGES")
        def paragraph(element):
            return "".join(node.text or "" if node.tag == namespace + "t" else "\t" if node.tag == namespace + "tab" else "\n" if node.tag == namespace + "br" else "" for node in element.iter())
        def blocks(element):
            if element.tag == namespace + "p":
                value = paragraph(element)
                if value.strip():
                    yield value
            elif element.tag == namespace + "tbl":
                for row in element.findall(namespace + "tr"):
                    yield " | ".join(" ".join(paragraph(p) for p in cell.iter(namespace + "p")) for cell in row.findall(namespace + "tc"))
            else:
                for child in element:
                    yield from blocks(child)
        return "\n".join(blocks(root))

    @staticmethod
    def _cda_inline(node):
        """Concatenate one cell's text preserving original spacing, so
        <content>124</content>/<content>73</content> renders as '124/73', and
        <br/> becomes a real line break (CDA narrative uses <br/>, not \\n)."""
        buffer = [node.text or ""]
        for child in node:
            if child.tag.rsplit("}", 1)[-1] == "br":
                buffer.append("\n")
            buffer.append(DocumentTextExtractor._cda_inline(child))
            buffer.append(child.tail or "")
        return "".join(buffer)

    @staticmethod
    def _cda_narrative(node):
        """Render a CDA <text> narrative subtree as readable clinical text.
        Table ROWS stay on one line so 'Blood Pressure: 124/73' is quotable.
        <list><item> stays one item per line - it is a block, not a row, and
        joining it the way <tr> is joined would collapse a whole medication
        list onto a single unreadable, unquotable line."""
        tidy = lambda s: "\n".join(" ".join(l.split()) for l in s.splitlines() if l.strip())
        local = node.tag.rsplit("}", 1)[-1]
        if local in {"table", "tbody", "thead", "tfoot", "list"}:
            return "\n".join(s for s in (DocumentTextExtractor._cda_narrative(c) for c in node) if s.strip())
        if local == "tr":
            cells = [tidy(DocumentTextExtractor._cda_inline(c)).replace("\n", " ") for c in node]
            cells = [c for c in cells if c]
            if not cells:
                return ""
            head, rest = cells[0].rstrip(":"), [c for c in cells[1:] if c not in ("-", "")]
            return f"{head}: " + " | ".join(rest) if rest else head
        # <item> is a BLOCK, not a row: its <br/>-separated lines must survive.
        if local == "item" or any(c.tag.rsplit("}", 1)[-1] in {"table", "list", "tbody"} for c in node.iter()):
            return "\n".join(s for s in (DocumentTextExtractor._cda_narrative(c) for c in node) if s.strip())
        return tidy(DocumentTextExtractor._cda_inline(node))

    @staticmethod
    def _xml_text(content) -> str:
        if isinstance(content, str):
            raw = content
        else:
            declaration = re.match(rb"\s*<\?xml[^>]*encoding=[\"']([^\"']+)", content[:256])
            charset = codecs.lookup(declaration.group(1).decode("ascii")).name if declaration else None
            raw = DocumentTextExtractor._decode(content, charset)
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I) or "\x00" in raw:
            raise DocumentProcessingError("UNSAFE_XML")
        root = ET.fromstring(raw)
        if any(node.tag.rsplit("}", 1)[-1] in {"Binary", "DocumentReference", "Media"} for node in root.iter()):
            raise DocumentProcessingError("ENCODED_DOCUMENT_REQUIRES_TRANSPORT_DECODING")
        # Clinical XML can carry the only diagnosis, value/unit or status in
        # attributes. Keep those values with structural context, not just itertext.
        #
        # Redundancy-only compression of the non-narrative walk (design doc:
        # care-capture-nodeapi .claude/debug-reports/2026-09-22-async-summarization-fix/
        # cda-redundancy-compression-design.md). Invariant R: tag/attribute NAMES
        # may influence layout (where a line lands, how long its path prefix is)
        # but never retention -- only mechanical redundancy is removed, so an
        # unknown schema degrades to more verbose output, never lossier output.
        # Three name-free rules:
        #   1. the highest node whose subtree emits <= _XML_GROUP_MAX_PARTS parts
        #      becomes a group, announced once by an "@ <full path>" header;
        #   2. body lines under a header carry the complete ancestor chain from
        #      the group root down (a full tail path -- never delta/indent-encoded,
        #      because _create_batches slices this text into stateless 30k-char
        #      chunks and every line must stay self-describing when its header
        #      lands in the previous chunk);
        #   3. the second and later occurrences of a byte-identical subtree
        #      emitting >= _XML_BLOCK_MIN_PARTS parts collapse to one
        #      "-> IDENTICAL TO #n" pointer at their own path; the first
        #      occurrence always renders in full, in place, anchored "{#n}"
        #      (multiplicity stays explicit: n occurrences = 1 full block +
        #      n-1 pointers).
        # Element text and _cda_narrative blocks are emitted byte-identically to
        # the ungrouped walk, at column 0, in document order -- the content
        # channel that verify_grounding quotes from is untouched.
        parts = []
        narrative_cache = {}

        def narrative(node):
            got = narrative_cache.get(id(node))
            if got is None:
                got = DocumentTextExtractor._cda_narrative(node).strip()
                narrative_cache[id(node)] = got
            return got

        def payload(node):
            """Marker prefix + surviving-attribute text for one node -- exactly
            the filtering the ungrouped walk applied.

            moodCode/negationInd/entryRelationship-typeCode: explicit semantic
            prefix instead of either a raw dump or silent suppression - see
            _XML_SEMANTIC_ATTRS above. EVN (or absent) and negationInd="false"
            (or absent) stay no-cost: nothing is emitted for the common case."""
            raw_attrs = {key.rsplit("}", 1)[-1]: value for key, value in node.attrib.items()}
            attributes = {key: value for key, value in raw_attrs.items()
                          if key not in _XML_NOISE_ATTRS and key not in _XML_SEMANTIC_ATTRS}
            markers = []
            mood = raw_attrs.get("moodCode")
            if mood in _XML_MOOD_PREFIXES:
                markers.append(_XML_MOOD_PREFIXES[mood])
            if raw_attrs.get("negationInd") == "true":
                markers.append("NEGATED:")
            if node.tag.rsplit("}", 1)[-1] == "entryRelationship":
                rel_type = raw_attrs.get("typeCode")
                if rel_type in _XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES:
                    markers.append(_XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES[rel_type])
            prefix = (" ".join(markers) + " ") if markers else ""
            attr_text = "; ".join(f"{key}={value}" for key, value in attributes.items())
            return prefix, attr_text

        emitted_cache = {}

        def emitted(node):
            """How many parts the ungrouped walk would emit for this subtree
            (the node's tail belongs to its parent, not to this count)."""
            got = emitted_cache.get(id(node))
            if got is not None:
                return got
            local = node.tag.rsplit("}", 1)[-1]
            if local in _XML_NOISE_TAGS:
                count = 0
            elif local == "text":
                count = 1 if narrative(node) else 0
            else:
                prefix, attr_text = payload(node)
                count = 1 if (attr_text or prefix) else 0
                if node.text and node.text.strip():
                    count += 1
                for child in node:
                    count += emitted(child)
                    if child.tail and child.tail.strip():
                        count += 1
            emitted_cache[id(node)] = count
            return count

        signature_cache = {}

        def signature(node):
            """Merkle sha256 over exactly what the subtree emits, relative to its
            own root: local tags (they appear in descendants' tail paths), marker
            prefixes, surviving-attribute text, element text, tails and rendered
            narrative. Computed from emitted content, never from a name-keyed
            decision: two subtrees share a signature only when they would render
            identically, byte for byte. Filtered noise contributes nothing, so
            subtrees differing only in noise still collapse; any structural
            difference at all keeps them apart (over-strict is the safe side)."""
            got = signature_cache.get(id(node))
            if got is not None:
                return got
            local = node.tag.rsplit("}", 1)[-1]
            hasher = hashlib.sha256()

            def feed(kind, value):
                data = value.encode("utf-8", "surrogatepass")
                hasher.update(f"{kind}{len(data)}:".encode())
                hasher.update(data)

            if local == "text":
                feed("n", narrative(node))
            elif local not in _XML_NOISE_TAGS:
                prefix, attr_text = payload(node)
                feed("g", local)
                feed("m", prefix)
                feed("a", attr_text)
                if node.text and node.text.strip():
                    feed("t", node.text.strip())
                for child in node:
                    if child.tag.rsplit("}", 1)[-1] not in _XML_NOISE_TAGS:
                        feed("c", signature(child))
                    if child.tail and child.tail.strip():
                        feed("l", child.tail.strip())
            digest = hasher.hexdigest()
            signature_cache[id(node)] = digest
            return digest

        block_counts = {}

        def census(node):
            local = node.tag.rsplit("}", 1)[-1]
            if local in _XML_NOISE_TAGS or local == "text":
                return
            if emitted(node) >= _XML_BLOCK_MIN_PARTS:
                sig = signature(node)
                block_counts[sig] = block_counts.get(sig, 0) + 1
            for child in node:
                census(child)

        census(root)
        block_ids = {}

        def block_ref(node):
            """None, or ("first", n): render in full anchored {#n}, or
            ("again", n): collapse to a pointer. _XML_BLOCK_MIN_PARTS keeps small
            clinical blocks (a 2-line criticality observation, a dose/route pair)
            out of the mechanism entirely, so exact-duplicate small facts always
            print in full at every occurrence."""
            if emitted(node) < _XML_BLOCK_MIN_PARTS:
                return None
            sig = signature(node)
            if block_counts.get(sig, 0) < 2:
                return None
            if sig in block_ids:
                return ("again", block_ids[sig])
            block_ids[sig] = len(block_ids) + 1
            return ("first", block_ids[sig])

        def labelled_children(node):
            """label(child) = tag, or tag[i] (1-based document position) when the
            parent has >= 2 children with that same tag. Labels land in group
            headers and spine paths only -- body tail paths stay exactly as
            ambiguous/unambiguous as the ungrouped walk's paths were."""
            names = [child.tag.rsplit("}", 1)[-1] for child in node]
            totals = {}
            for name in names:
                totals[name] = totals.get(name, 0) + 1
            seen = {}
            out = []
            for child, name in zip(node, names):
                seen[name] = seen.get(name, 0) + 1
                out.append((child, f"{name}[{seen[name]}]" if totals[name] > 1 else name))
            return out

        def render_body(node, tail):
            """One line per node inside a group: today's line with the group
            root's path prefix removed -- the complete remaining ancestor chain,
            nothing else omitted."""
            local = node.tag.rsplit("}", 1)[-1]
            if local in _XML_NOISE_TAGS:
                return
            if local == "text":
                # CDA narrative block: render with row/item adjacency preserved
                # instead of one XPath-scaffold line per text node.
                rendered = narrative(node)
                if rendered:
                    parts.append(rendered)
                return
            tail_path = "/".join(tail)
            ref = block_ref(node)
            if ref and ref[0] == "again":
                parts.append(f"{tail_path} -> IDENTICAL TO #{ref[1]}")
                return
            suffix = f" {{#{ref[1]}}}" if ref else ""
            prefix, attr_text = payload(node)
            if attr_text:
                parts.append(prefix + tail_path + ": " + attr_text + suffix)
            elif prefix:
                # No other attribute survives noise-filtering, but the semantic
                # marker itself must not be silently dropped.
                parts.append(prefix + tail_path + suffix)
            elif suffix:
                # A duplicated block whose root emits no line of its own still
                # needs its "{#n}" anchor so later pointers resolve.
                parts.append(tail_path + suffix)
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            for child in node:
                render_body(child, (*tail, child.tag.rsplit("}", 1)[-1]))
                if child.tail and child.tail.strip():
                    parts.append(child.tail.strip())

        def segment(node, chain, label):
            local = node.tag.rsplit("}", 1)[-1]
            if local in _XML_NOISE_TAGS:
                return
            if local == "text":
                rendered = narrative(node)
                if rendered:
                    parts.append(rendered)
                return
            if not emitted(node):
                return  # emits nothing in the ungrouped walk -> emits nothing now
            full_path = "/".join((*chain, label))
            ref = block_ref(node)
            if ref and ref[0] == "again":
                parts.append(f"@ {full_path} -> IDENTICAL TO #{ref[1]}")
                return
            suffix = f" {{#{ref[1]}}}" if ref else ""
            prefix, attr_text = payload(node)
            if emitted(node) <= _XML_GROUP_MAX_PARTS:
                # Group root: one "@" header carrying the full path plus the
                # root's own markers/attributes (a group root must not lose its
                # payload to the header); body lines carry tail paths only.
                header = "@ " + prefix + full_path
                if attr_text:
                    header += ": " + attr_text
                parts.append(header + suffix)
                if node.text and node.text.strip():
                    parts.append(node.text.strip())
                for child in node:
                    render_body(child, (child.tag.rsplit("}", 1)[-1],))
                    if child.tail and child.tail.strip():
                        parts.append(child.tail.strip())
                return
            # Spine node (subtree too large for one group, rare): its own line
            # keeps the full path; recurse to find group roots below.
            if attr_text:
                parts.append(prefix + full_path + ": " + attr_text + suffix)
            elif prefix:
                parts.append(prefix + full_path + suffix)
            elif suffix:
                parts.append(full_path + suffix)
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            for child, child_label in labelled_children(node):
                segment(child, (*chain, label), child_label)
                if child.tail and child.tail.strip():
                    parts.append(child.tail.strip())

        segment(root, (), root.tag.rsplit("}", 1)[-1])
        return "\n".join(parts)

    @staticmethod
    def _html_text(raw: str) -> str:
        class VisibleText(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.parts, self.hidden = [], []
            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                style = (attributes.get("style") or "").replace(" ", "").lower()
                void = tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
                if not void and (self.hidden or tag in {"script", "style", "template", "noscript"} or "hidden" in attributes or "display:none" in style or "visibility:hidden" in style):
                    self.hidden.append(tag)
                if tag == "img" and not self.hidden:
                    from src.app.services.document_image_routing import html_image_is_decorative
                    if not html_image_is_decorative(attributes, text_seen=bool(self.parts)):
                        self.parts.append("[Embedded image not transcribed]")
            def handle_endtag(self, tag):
                if self.hidden and tag == self.hidden[-1]:
                    self.hidden.pop()
            def handle_data(self, data):
                if not self.hidden and data.strip():
                    self.parts.append(data.strip())
        parser = VisibleText()
        parser.feed(raw)
        parser.close()
        if parser.hidden:
            raise DocumentProcessingError("PARSE_FAILED")
        text = "\n".join(parser.parts)
        if re.search(r"\b(?:403 forbidden|401 unauthorized|502 bad gateway|503 service unavailable|access denied|please sign in|login required)\b", text[:1500], re.I):
            raise DocumentProcessingError("NON_CLINICAL_ERROR_DOCUMENT")
        return text

    def _extract_from_rtf(self, content: bytes, file_name=None, charset=None) -> str:
        from striprtf.striprtf import rtf_to_text
        content = content.removeprefix(codecs.BOM_UTF8).lstrip()
        if not content.startswith(self.RTF_MAGIC):
            raise DocumentProcessingError("MIME_MISMATCH")
        match = re.search(rb"\\ansicpg(\d+)", content[:1024])
        encoding = f"cp{match.group(1).decode()}" if match else charset or "cp1252"
        raw = self._decode(content, encoding)
        if charset and match and any(byte >= 128 for byte in content):
            if self._decode(content, charset) != raw:
                raise DocumentProcessingError("CONFLICTING_ENCODING")
        depth = 0
        for token in re.finditer(r"\\(?:[\\{}]|'[0-9a-fA-F]{2})|[{}]", raw):
            if token.group() == "{":
                depth += 1
            elif token.group() == "}":
                depth -= 1
            if depth < 0 or depth > 256:
                raise DocumentProcessingError("MALFORMED_RTF")
        if depth or re.search(r"\\(?:object|objdata|bin)\b", raw):
            raise DocumentProcessingError("UNSUPPORTED_EMBEDDED_CONTENT" if not depth else "MALFORMED_RTF")
        text = rtf_to_text(raw, encoding=encoding, errors="strict")
        return text + "\n[Embedded image not transcribed]" if re.search(r"\\pict\b", raw) else text

    def _extract_from_txt(self, content: bytes, file_name=None) -> str:
        return self.validate_text(self._decode(content))

    def _extract_from_xml(self, content: bytes, file_name=None) -> str:
        return self.validate_text(self._xml_text(content))

    def _extract_from_html(self, content: bytes, file_name=None) -> str:
        return self.validate_text(self._html_text(self._decode(content)))

    def _infer_type_from_filename(self, file_name: str) -> str:
        mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        return self.ALIASES.get(mime, mime)

    async def extract_text_async(self, content: bytes, content_type: str, file_name=None) -> str:
        # Killable isolated process: cancellation/deadline must stop native parsers too.
        import sys
        if not isinstance(content, bytes):
            raise DocumentProcessingError("INVALID_CONTENT")
        if len(content) > self.MAX_FILE_SIZE:
            raise DocumentProcessingError("FILE_TOO_LARGE")
        options = {"disabled_adapters": sorted(self.disabled_adapters), "transport_enabled": self.transport_enabled, "allow_containers": self.allow_containers}
        limits = {name: getattr(self, name) for name in ("MAX_FILE_SIZE", "MAX_TEXT_CHARS", "MAX_PAGES", "MAX_ZIP_ENTRIES", "MAX_ARCHIVE_EXPANDED_BYTES", "MAX_ARCHIVE_DEPTH")}
        import tempfile
        # Parent owns the directory so SIGKILL of a native parser cannot leave source files.
        with tempfile.TemporaryDirectory(prefix="document-parser-") as workspace:
            async with _PARSER_SLOTS:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "src.app.services.document_parser_worker",
                    content_type or "application/octet-stream", file_name or "", json.dumps({"options": options, "limits": limits, "workspace": workspace}), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
                try:
                    output, _ = await asyncio.wait_for(process.communicate(content), timeout=30)
                    if process.returncode:
                        raise DocumentProcessingError("PARSER_PROCESS_FAILED")
                    result = json.loads(output)
                    if "error" in result:
                        if result["error"] == "OCR_REQUIRED":
                            from src.app.services.document_ocr import extract_scanned_document
                            return await extract_scanned_document(content, content_type)
                        raise DocumentProcessingError(result["error"])
                    return self.validate_text(result["text"])
                except TimeoutError as exc:
                    raise DocumentProcessingError("PARSER_TIMEOUT") from exc
                finally:
                    # Kill the process group too: native converters must not outlive cancellation.
                    import os
                    import signal
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()


_PARSER_SLOTS = asyncio.Semaphore(2)
