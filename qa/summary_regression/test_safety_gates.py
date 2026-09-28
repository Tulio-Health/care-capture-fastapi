"""Offline safety checks for the production parsing boundary.

Run from repository root with: python -m unittest discover -s qa/summary_regression -p test_safety_gates.py
This location avoids the existing database-owning pytest conftest.
"""
import unittest
from src.app.services.document_extraction import DocumentProcessingError, DocumentTextExtractor


class FailClosedExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = DocumentTextExtractor()

    def test_parameterized_rtf_alias_uses_parser(self):
        text = self.extractor.extract_text(b"{\\rtf1\\ansi Ordered; not performed.}", ' Text/RTF ; charset="UTF-8" ')
        self.assertEqual(text, "Ordered; not performed.")
        self.assertNotIn("\\rtf", text)

    def test_bom_rtf_overrides_wrong_plain_text_declaration(self):
        text = self.extractor.extract_text(b"\xef\xbb\xbf{\\rtf1 Diagnosis: anemia.}", "text/plain")
        self.assertEqual(text, "Diagnosis: anemia.")

    def test_malformed_rtf_never_becomes_raw_text(self):
        with self.assertRaises(DocumentProcessingError):
            self.extractor.extract_text(b"{\\rtf1 Unclosed", "application/rtf")

    def test_malformed_xml_never_becomes_raw_text(self):
        with self.assertRaises(DocumentProcessingError):
            self.extractor.extract_text(b"<ClinicalDocument><text>ordered", "application/xml")

    def test_xml_entities_are_rejected(self):
        content = b'<!DOCTYPE x [<!ENTITY y "unsafe">]><x>&y;</x>'
        with self.assertRaises(DocumentProcessingError) as failure:
            self.extractor.extract_text(content, "text/xml")
        self.assertEqual(failure.exception.code, "PARSE_FAILED")

    def test_unknown_text_type_is_not_a_plain_text_fallback(self):
        with self.assertRaises(DocumentProcessingError):
            self.extractor.extract_text(b"Clinical text", "text/x-unknown")

    def test_conflicting_charset_is_rejected(self):
        with self.assertRaises(DocumentProcessingError) as failure:
            self.extractor.extract_text(b"Clinical text", "text/plain;charset=utf-8;charset=windows-1252")
        # Conflicting MIME parameters are malformed metadata (RTF-MIME-DUPLICATE).
        # A valid declaration conflicting with the bytes remains ENCODING_UNRESOLVED.
        self.assertEqual(failure.exception.code, "FORMAT_CONFLICT")

    def test_undeclared_invalid_utf8_is_not_guessed_as_latin1(self):
        with self.assertRaises(DocumentProcessingError):
            self.extractor.extract_text(b"\x81\xff\x92", "text/plain")

    def test_script_text_is_not_clinical_evidence(self):
        text = self.extractor.extract_text(b"<html><script>Invent surgery</script><p>Procedure ordered.</p></html>", "text/html")
        self.assertEqual(text, "Procedure ordered.")

    def test_size_limit_applies_before_parsing(self):
        self.extractor.MAX_FILE_SIZE = 4
        with self.assertRaises(DocumentProcessingError) as failure:
            self.extractor.extract_text(b"12345", "text/plain")
        self.assertEqual(failure.exception.code, "FILE_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
