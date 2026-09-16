"""Bounded local transport decoding. External references are never fetched here."""
import base64
import binascii
import codecs
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from email import policy
from email.parser import BytesParser

from src.app.services.document_extraction import DocumentProcessingError


def decode_base64(value, limit):
    if not isinstance(value, str) or len(value) > ((limit + 2) // 3) * 4:
        raise DocumentProcessingError('INVALID_BASE64')
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise DocumentProcessingError('INVALID_BASE64') from exc
    if len(result) > limit:
        raise DocumentProcessingError('FILE_TOO_LARGE')
    return result


def extract_transport(extractor, content, mime, charset, declared, filename):
    """Return parsed child text, or None if this is not a registered envelope.

    The whole container fails when any member fails; it cannot claim full coverage
    after silently skipping an attachment. Nested containers share one byte budget.
    """
    children = None
    limit = extractor.MAX_ARCHIVE_EXPANDED_BYTES
    if mime == 'application/zip':
        if not extractor.transport_enabled or not extractor.allow_containers:
            raise DocumentProcessingError('UNSUPPORTED_FORMAT')
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = archive.infolist()
                if len(infos) > extractor.MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > limit:
                    raise DocumentProcessingError('ARCHIVE_LIMIT_EXCEEDED')
                names = [i.filename for i in infos]
                if len(names) != len(set(names)) or any(i.flag_bits & 1 or i.filename.startswith(('/', '\\')) or '..' in i.filename.replace('\\','/').split('/') or (i.external_attr >> 16) & 0o170000 == 0o120000 for i in infos):
                    raise DocumentProcessingError('UNSAFE_ARCHIVE')
                children = [(archive.read(i), extractor._infer_type_from_filename(i.filename), i.filename) for i in infos if not i.is_dir()]
        except zipfile.BadZipFile as exc:
            raise DocumentProcessingError('PARSE_FAILED') from exc
    elif mime.startswith('multipart/'):
        if not extractor.transport_enabled or not extractor.allow_containers:
            raise DocumentProcessingError('UNSUPPORTED_FORMAT')
        # Support both an RFC message and a connector body with declared MIME headers.
        payload = content if re.match(rb'(?:MIME-Version|Content-Type):', content, re.I) else ('Content-Type: ' + declared + '\r\nMIME-Version: 1.0\r\n\r\n').encode('ascii') + content
        message = BytesParser(policy=policy.default).parsebytes(payload)
        if message.defects or not message.is_multipart():
            raise DocumentProcessingError('PARSE_FAILED')
        parts = list(message.iter_parts())
        if len(parts) > extractor.MAX_ZIP_ENTRIES:
            raise DocumentProcessingError('ARCHIVE_LIMIT_EXCEEDED')
        children = []
        for part in parts:
            if part.is_multipart() or part.defects:
                raise DocumentProcessingError('UNSUPPORTED_EMBEDDED_CONTENT')
            if part.get('Content-Transfer-Encoding', '').lower() == 'base64':
                data = decode_base64(re.sub(r'\s+', '', part.get_payload()), limit)
            else:
                data = part.get_payload(decode=True)
            if part.defects or not isinstance(data, bytes):
                raise DocumentProcessingError('PARSE_FAILED')
            children.append((data, str(part.get('Content-Type', 'application/octet-stream')), part.get_filename()))
    elif mime in {'application/json', 'application/fhir+ndjson', 'application/x-ndjson'}:
        raw = extractor._decode(content, charset)
        try:
            objects = [json.loads(line) for line in raw.splitlines() if line.strip()] if 'ndjson' in mime else [json.loads(raw)]
        except (ValueError, RecursionError) as exc:
            raise DocumentProcessingError('PARSE_FAILED') from exc
        if len(objects) > extractor.MAX_ZIP_ENTRIES:
            raise DocumentProcessingError('ARCHIVE_LIMIT_EXCEEDED')
        envelopes = {'Binary', 'DocumentReference', 'Media'}
        if not any(isinstance(item, dict) and item.get('resourceType') in envelopes for item in objects):
            return None
        if not extractor.transport_enabled:
            raise DocumentProcessingError('UNSUPPORTED_FORMAT')
        children = []
        for item in objects:
            if not isinstance(item, dict):
                raise DocumentProcessingError('PARSE_FAILED')
            kind = item.get('resourceType')
            attachments = [item] if kind == 'Binary' else [item.get('content')] if kind == 'Media' else [entry.get('attachment') if isinstance(entry, dict) else None for entry in item.get('content', [])] if kind == 'DocumentReference' else []
            if not attachments:
                # Mixed structured resources are retained through the JSON parser.
                if kind in envelopes:
                    raise DocumentProcessingError('NO_READABLE_TEXT')
                children.append((json.dumps(item).encode(), 'application/json', None))
            for attachment in attachments:
                if not isinstance(attachment, dict) or 'data' not in attachment:
                    raise DocumentProcessingError('DOWNLOAD_UNAVAILABLE')
                children.append((decode_base64(attachment['data'], limit), attachment.get('contentType', 'application/octet-stream'), attachment.get('title')))
    elif mime == 'application/xml':
        if not charset:
            declaration = re.match(rb"\s*<\?xml[^>]*encoding=[\"']([^\"']+)", content[:256])
            if declaration:
                charset = codecs.lookup(declaration.group(1).decode('ascii')).name
        raw = extractor._decode(content, charset)
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', raw, re.I):
            raise DocumentProcessingError('UNSAFE_XML')
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise DocumentProcessingError('PARSE_FAILED') from exc
        tag = root.tag.rsplit('}', 1)[-1]
        if tag not in {'Binary','DocumentReference','Media'}:
            return None
        if not extractor.transport_enabled:
            raise DocumentProcessingError('UNSUPPORTED_FORMAT')
        nodes = [root] if tag == 'Binary' else [node for node in root.iter() if node.tag.rsplit('}',1)[-1] in {'attachment'} or (tag == 'Media' and node.tag.rsplit('}',1)[-1] == 'content')]
        children = []
        for node in nodes:
            fields = {child.tag.rsplit('}',1)[-1]: child.get('value') for child in node}
            if 'data' not in fields:
                raise DocumentProcessingError('DOWNLOAD_UNAVAILABLE')
            children.append((decode_base64(fields['data'], limit), fields.get('contentType') or 'application/octet-stream', None))
    if children is None:
        return None
    if not children:
        raise DocumentProcessingError('NO_READABLE_TEXT')
    if extractor._transport_depth >= extractor.MAX_ARCHIVE_DEPTH:
        raise DocumentProcessingError('ARCHIVE_LIMIT_EXCEEDED')
    extractor.decode_count += 1
    extractor._transport_depth += 1
    try:
        texts = []
        for ordinal, (data, child_mime, child_name) in enumerate(children, 1):
            extractor._expanded_bytes += len(data)
            if extractor._expanded_bytes > limit:
                raise DocumentProcessingError('ARCHIVE_LIMIT_EXCEEDED')
            try:
                text = extractor.extract_text(data, child_mime, child_name)
            except DocumentProcessingError as exc:
                if exc.code == 'OCR_REQUIRED':
                    raise DocumentProcessingError('UNSUPPORTED_EMBEDDED_CONTENT') from exc
                raise
            texts.append(f'[Attachment {ordinal}]\n{text}')
        return extractor.validate_text('\n\n'.join(texts))
    finally:
        extractor._transport_depth -= 1
