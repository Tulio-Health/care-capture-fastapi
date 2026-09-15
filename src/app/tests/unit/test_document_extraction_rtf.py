"""RTF routing in DocumentTextExtractor: raw RTF must not reach the LLM as markup.

The prod artifact this fixture mimics is an Epic-exported Binary with no file
extension and an unreliable declared contentType - see
care-capture-nodeapi/.claude/debug-reports/2026-09-08-summary-fix-plan/revision-round3.md
(PR-1) for the full spec these tests implement.
"""

import os

import boto3
import pytest

from src.app.services.document_extraction import DocumentTextExtractor

# Epic-shaped: custom control word, font table, hex escape, real clinical line.
RTF = (
    rb"{\rtf1\epicV11702\ansi\ansicpg1252\deff0"
    rb"{\fonttbl{\f0\fswiss\fcharset0 Arial;}{\f1\fmodern Courier New;}}"
    rb"{\colortbl ;\red0\green0\blue0;}"
    rb"{\*\generator Epic;}"
    rb"\pard\f0\fs20 Assessment/Plan\par "
    rb"Return in about 1 year (around 7/30/2027) for preventative, sooner prn.\par}"
)

# Same Epic-shaped body, but prefixed with a UTF-8 BOM (real Windows/Epic exporters do
# emit this). content.lstrip() strips ASCII whitespace only, so content.lstrip()[:5] is
# b"\xef\xbb\xbf{\\r" != RTF_MAGIC - the sniff misses and only the text/rtf MIME arm can
# route this correctly.
RTF_WITH_BOM = b"\xef\xbb\xbf" + RTF


def test_rtf_is_sniffed_even_when_declared_text_plain():
    # Prod shape: no file extension, contentType not trustworthy.
    out = DocumentTextExtractor().extract_text(
        RTF, "text/plain", "1788806346365_f5Cr3BZPgnk84"
    )
    assert "Return in about 1 year" in out
    assert "Assessment/Plan" in out
    assert "rtf1" not in out and "fonttbl" not in out and "epicV11702" not in out
    assert len(out) < len(RTF) / 2  # markup actually removed, not just passed through


def test_declared_rtf_mime_no_longer_raises():
    out = DocumentTextExtractor().extract_text(RTF, "application/rtf", "note.rtf")
    assert "Return in about 1 year" in out


def test_bom_prefixed_rtf_is_routed_by_mime_arm_not_sniff():
    # The sniff branch misses this fixture (BOM shifts the magic bytes), so this only
    # passes if the text/rtf MIME arm exists AND is placed before the text/ startswith
    # fallback at extract_text's routing chain - it fails on today's code (falls to
    # _extract_from_txt -> markup passthrough) and fails if the MIME arm is placed after
    # the text/ fallback.
    out = DocumentTextExtractor().extract_text(RTF_WITH_BOM, "text/rtf", "note.rtf")
    assert "Return in about 1 year" in out
    assert "Assessment/Plan" in out
    assert "fonttbl" not in out


CARE_CAPTURE_RTF_FIXTURE_S3_KEY = os.getenv("CARE_CAPTURE_RTF_FIXTURE_S3_KEY")
CARE_CAPTURE_RTF_FIXTURE_S3_BUCKET = os.getenv(
    "CARE_CAPTURE_RTF_FIXTURE_S3_BUCKET", "carecapture-prod-storage"
)

requires_s3 = pytest.mark.skipif(
    not CARE_CAPTURE_RTF_FIXTURE_S3_KEY,
    reason="CARE_CAPTURE_RTF_FIXTURE_S3_KEY not set in this environment - skipping "
    "live-artifact RTF extraction merge gate.",
)


@requires_s3
def test_extract_from_rtf_against_real_prod_artifact():
    """RR-10's merge gate, executable: striprtf's fidelity on Epic's dialect is
    unverified against the real artifact until this runs. GETs the real prod object
    and asserts the three known landmarks survive extraction.

    Skipped in CI (no key set). Run locally before merging PR-1 - see
    scripts/verify_rtf_extraction.py for the same check outside pytest.
    """
    s3 = boto3.client("s3")
    response = s3.get_object(
        Bucket=CARE_CAPTURE_RTF_FIXTURE_S3_BUCKET, Key=CARE_CAPTURE_RTF_FIXTURE_S3_KEY
    )
    content = response["Body"].read()

    out = DocumentTextExtractor()._extract_from_rtf(
        content, CARE_CAPTURE_RTF_FIXTURE_S3_KEY
    )

    assert "Assessment/Plan" in out
    assert "Follow up" in out
    assert "Return in" in out
