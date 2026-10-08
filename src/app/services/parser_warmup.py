"""Startup parser warm-up: parse one tiny embedded PDF/HTML/XML sample through the real
extractor (same killable worker subprocess as production) so the first real documents do not
pay the cold-import / cold-disk cost (observed as exact 30 s PARSER_TIMEOUT steps on a freshly
booted instance). Offline only; never raises; bounded by WARMUP_TIMEOUT_S."""

import asyncio
import time

from src.app.common.logging import get_logger

logger = get_logger(__name__)

WARMUP_TIMEOUT_S = 25


def _tiny_pdf() -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 12 Tf 10 50 Td (Parser warmup sample) Tj ET"
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    return bytes(out)


_HTML = b"<html><body><h1>Progress Note</h1><p>Parser warmup sample.</p></body></html>"
_XML = (
    b'<?xml version="1.0"?><ClinicalDocument xmlns="urn:hl7-org:v3"><title>Warmup</title>'
    b"<component><structuredBody><component><section><title>Sample</title>"
    b"<text>Parser warmup sample.</text></section></component></structuredBody></component>"
    b"</ClinicalDocument>"
)


async def _run() -> list:
    from src.app.services.document_extraction import DocumentTextExtractor

    extractor = DocumentTextExtractor()
    done = []
    for name, content, mime in (
        ("pdf", _tiny_pdf(), "application/pdf"),
        ("html", _HTML, "text/html"),
        ("xml", _XML, "application/xml"),
    ):
        try:
            await extractor.extract_text_async(content, mime, f"warmup.{name}")
            done.append(name)
        except Exception as exc:  # warm-up is best-effort
            logger.warning(
                "parser_warmup %s failed error_type=%s", name, type(exc).__name__
            )
    return done


async def warm_up_parsers() -> None:
    started = time.monotonic()
    try:
        done = await asyncio.wait_for(_run(), timeout=WARMUP_TIMEOUT_S)
        status = "done"
    except Exception as exc:
        done, status = [], f"failed error_type={type(exc).__name__}"
    logger.info(
        "parser_warmup %s ms=%d parsers=%s",
        status,
        int((time.monotonic() - started) * 1000),
        ",".join(done),
    )
