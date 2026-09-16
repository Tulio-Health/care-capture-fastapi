"""Fail-closed document extraction. No raw-document fallback is permitted."""
from __future__ import annotations

import asyncio
import codecs
import csv
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
            "RESOURCE_LIMIT_EXCEEDED": {"TEXT_LIMIT_EXCEEDED", "PAGE_LIMIT_EXCEEDED", "ARCHIVE_LIMIT_EXCEEDED", "IMAGE_PIXEL_LIMIT_EXCEEDED", "OCR_PAGE_LIMIT_EXCEEDED", "OCR_RENDER_LIMIT_EXCEEDED", "COMPRESSION_LIMIT_EXCEEDED", "DOCUMENT_LIMIT_EXCEEDED", "CHUNK_LIMIT_EXCEEDED", "SYNTHESIS_BUDGET_EXCEEDED", "SYNTHESIS_RECORD_LIMIT_EXCEEDED", "PROCEDURE_CONTEXT_LIMIT_EXCEEDED", "TRANSCRIPT_CONTEXT_LIMIT_EXCEEDED", "FHIR_CONTEXT_LIMIT_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED", "VALIDATION_BUDGET_EXCEEDED", "SUMMARY_BUSY", "DOWNLOAD_BUSY"},
            "MODEL_OUTPUT_INVALID": {"MODEL_SOURCE_RECONCILIATION_FAILED", "OCR_INCOMPLETE_RESPONSE", "CLASSIFICATION_ID_MISMATCH"},
            "CLINICAL_EVIDENCE_FAILED": {"GROUNDING_VALIDATION_FAILED", "INVALID_SOURCE_EVIDENCE", "DIAGNOSIS_WORDING_NOT_GROUNDED", "PROCEDURE_STATUS_NOT_GROUNDED"},
            "DOWNLOAD_PENDING": {"DOCUMENT_NOT_READY"},
            "DOWNLOAD_UNAVAILABLE": {"MISSING_DOCUMENT_PATH"},
            "INTERNAL_PROCESSING_ERROR": {"INVALID_METADATA", "INVALID_CONTENT", "INVALID_INLINE_CONTENT", "INVALID_BASE64", "DOCUMENT_PROCESSING_FAILED"},
        }
        self.reason_code = code
        self.code = next((canonical for canonical, members in groups.items() if code in members), code)
        super().__init__(self.code)


class DocumentTextExtractor:
    MAX_FILE_SIZE = 50 * 1024 * 1024
    MAX_TEXT_CHARS = 1_000_000
    MAX_PAGES = 300
    MAX_ZIP_ENTRIES = 2000
    MAX_ARCHIVE_EXPANDED_BYTES = 50 * 1024 * 1024
    RTF_MAGIC = b"{\\rtf"
    VERSION = "strict-1"
    MAX_ARCHIVE_DEPTH = 2

    def __init__(self, *, disabled_adapters=(), transport_enabled=False, allow_containers=False):
        self.disabled_adapters = frozenset(disabled_adapters)
        self.last_adapter = None
        self.declared_mime = None
        self.detected_mime = None
        self.transport_enabled = transport_enabled
        self.allow_containers = allow_containers
        self.decode_count = 0
        self._transport_depth = 0
        self._expanded_bytes = 0

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
        if content.startswith(b"\x1f\x8b"):
            if not self.transport_enabled:
                raise DocumentProcessingError("UNSUPPORTED_FORMAT")
            import gzip
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as compressed:
                    expanded = compressed.read(self.MAX_FILE_SIZE + 1)
            except Exception as exc:
                raise DocumentProcessingError("INVALID_COMPRESSION") from exc
            if len(expanded) > self.MAX_FILE_SIZE or expanded.startswith(b"\x1f\x8b"):
                raise DocumentProcessingError("COMPRESSION_LIMIT_EXCEEDED")
            inner_name = file_name[:-3] if file_name and file_name.lower().endswith(".gz") else file_name
            inner_mime = "application/octet-stream" if mime in {"application/gzip", "application/x-gzip"} else content_type
            self.decode_count += 1
            return self.extract_text(expanded, inner_mime, inner_name)
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
                        if not self.transport_enabled or not self.allow_containers:
                            raise DocumentProcessingError("UNSUPPORTED_ARCHIVE")
                        detected = "application/zip"
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
            raise DocumentProcessingError("UNSUPPORTED_LEGACY_OFFICE")
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
        adapter = {"application/pdf": "pdf", "application/rtf": "rtf", "application/xml": "xml", "text/html": "html", "application/json": "json", "text/csv": "csv", "text/tab-separated-values": "csv", "text/plain": "text", "text/markdown": "text", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}.get(mime)
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
                    def parse_nested_text(value):
                        if isinstance(value, dict):
                            return {key: parse_nested_text(child) for key, child in value.items()}
                        if isinstance(value, list):
                            return [parse_nested_text(child) for child in value]
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
                # Embedded scans may contain the only clinical evidence. Do not silently omit them.
                if not text.strip() or page.get_images():
                    raise DocumentProcessingError("OCR_REQUIRED")
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
            if any(n.startswith("word/media/") for n in names):
                raise DocumentProcessingError("OCR_REQUIRED")
            parts = []
            for name in names:
                if name == "word/document.xml" or re.fullmatch(r"word/(?:header\d*|footer\d*|footnotes|endnotes)\.xml", name):
                    parts.append(self._word_text(archive.read(name)))
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
        parts = []
        def walk(node, ancestors=()):
            local = node.tag.rsplit("}", 1)[-1]
            path = (*ancestors, local)
            if node.attrib:
                attributes = "; ".join(f"{key.rsplit('}', 1)[-1]}={value}" for key, value in node.attrib.items())
                parts.append("/".join(path) + ": " + attributes)
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            for child in node:
                walk(child, path)
                if child.tail and child.tail.strip():
                    parts.append(child.tail.strip())
        walk(root)
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
                    raise DocumentProcessingError("OCR_REQUIRED")
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
        if depth or re.search(r"\\(?:object|objdata|bin|pict)\b", raw):
            raise DocumentProcessingError("UNSUPPORTED_EMBEDDED_CONTENT" if not depth else "MALFORMED_RTF")
        return rtf_to_text(raw, encoding=encoding, errors="strict")

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
        async with _PARSER_SLOTS:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "src.app.services.document_parser_worker",
                content_type or "application/octet-stream", file_name or "", json.dumps({"options": options, "limits": limits}), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
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
                if process.returncode is None:
                    process.kill()
                await process.wait()


_PARSER_SLOTS = asyncio.Semaphore(2)
