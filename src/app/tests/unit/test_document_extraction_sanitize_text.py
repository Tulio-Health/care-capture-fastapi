"""Unit tests for `DocumentTextExtractor.validate_text`'s sanitize-and-revalidate path.

round9-revision3.md Sec 3.2 step 2 (Fix 2). Root cause: all 27 dev EXTRACTION_QUALITY_FAILED
failures are text/plain x Admission Note Physician, rejected outright by the old all-or-nothing
check on a single stray control char or U+FFFD replacement character. This replaces that with
strip-then-density-gate, while keeping the raw-markup detectors (%PDF-, {\\rtf, html/xml) running
against the ORIGINAL text so sanitization can never mask genuine binary-format leakage.
"""
import pytest

from src.app.services.document_extraction import DocumentProcessingError, DocumentTextExtractor


def test_sanitization_strips_control_chars_but_preserves_newline_tab_cr():
    # \x00/\x07 are control chars outside \n\r\t; a single stray byte on an otherwise long
    # clinical note stays well under the 1% density threshold.
    text = "Admission Note\n\x00Patient stable\tBP 120/80\r\n" + ("x" * 200) + "\x07"
    out = DocumentTextExtractor.validate_text(text)
    assert "\x00" not in out and "\x07" not in out
    assert "\n" in out and "\t" in out and "\r" in out
    assert "Admission Note" in out and "Patient stable" in out and "BP 120/80" in out


def test_u_fffd_replacement_chars_are_stripped_under_density_threshold():
    text = "Clinical note with one stray mojibake byte here: \ufffd end of note. " + ("y" * 200)
    out = DocumentTextExtractor.validate_text(text)
    assert "\ufffd" not in out
    assert "end of note" in out


def test_empty_after_sanitization_still_raises_invalid_text():
    # Every character is junk -> sanitized text is empty -> must still fail closed.
    text = "\x00\x01\x02\ufffd\x03"
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.code == "EXTRACTION_QUALITY_FAILED"
    assert excinfo.value.reason_code == "INVALID_TEXT"


def test_density_threshold_rejects_when_too_much_of_the_document_is_junk():
    # 10 junk chars out of 20 total = 50% density, far over the ~1% starting threshold ->
    # this is mojibake/binary, not a document with one stray byte, so it must still fail.
    text = ("\x00" * 10) + ("a" * 10)
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.reason_code == "INVALID_TEXT"


def test_density_threshold_accepts_when_junk_is_a_small_fraction():
    # 1 junk char out of 1000+ chars is well under 1% -> sanitize and continue.
    text = "a" * 999 + "\x00" + "b" * 1
    out = DocumentTextExtractor.validate_text(text)
    assert "\x00" not in out
    assert len(out) == 1000


def test_raw_markup_checks_still_fire_on_original_text_even_when_sanitized_copy_would_pass():
    """A %PDF- document with injected control chars must still raise UNPARSED_CONTENT (the
    raw-binary-leakage signal), not be sanitized into something that slips past the markup
    detector and gets treated as clean text. This is the §5-E4-adjacent ordering constraint:
    raw-markup checks run on the ORIGINAL text before any sanitization is applied.
    """
    text = "%PDF-1.4\x00\x01 some binary-looking payload here " + ("z" * 200)
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.code == "EXTRACTION_QUALITY_FAILED"
    assert excinfo.value.reason_code == "UNPARSED_CONTENT"


def test_rtf_header_with_control_chars_still_raises_unparsed_content():
    text = "{\\rtf1\x00\x01\\ansi some payload " + ("z" * 200)
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.reason_code == "UNPARSED_CONTENT"


def test_html_leakage_with_control_chars_still_raises_unparsed_content():
    text = "<html>\x00<body>content</body></html>" + ("z" * 200)
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.reason_code == "UNPARSED_CONTENT"


def test_clean_text_with_no_junk_is_unaffected():
    text = "Admission Note Physician\nPatient is stable.\n"
    out = DocumentTextExtractor.validate_text(text)
    assert out == text.strip()


def test_still_raises_empty_text_for_whitespace_only_input():
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text("   \n\t  ")
    assert excinfo.value.reason_code == "EMPTY_TEXT"


def test_still_raises_text_limit_exceeded_before_sanitizing():
    text = "a" * (DocumentTextExtractor.MAX_TEXT_CHARS + 1)
    with pytest.raises(DocumentProcessingError) as excinfo:
        DocumentTextExtractor.validate_text(text)
    assert excinfo.value.reason_code == "TEXT_LIMIT_EXCEEDED"
