"""PR-10 regression coverage: decorative embedded images must not reject documents
that carry real clinical text. Synthetic, PHI-free fixtures only."""
import unittest
from unittest.mock import AsyncMock, patch

from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError


class EmbeddedImageExtractionSafety(unittest.TestCase):
    def test_html_letterhead_image_does_not_reject_the_document(self):
        filler = " ".join(f"Vitals recorded stable at check {i}." for i in range(220))
        html = (
            "<html><body>"
            '<img src="logo.png" width="120" height="40">'
            f"<p>Tdap vaccine administered on 03/14/2024. Medication: Lisinopril 10mg daily. {filler}</p>"
            "</body></html>"
        )
        self.assertGreaterEqual(len(html), 2000)
        text = DocumentTextExtractor().extract_text(html.encode(), "text/html")
        self.assertIn("Tdap vaccine administered", text)
        self.assertIn("Lisinopril 10mg", text)

    def test_rtf_pict_letterhead_does_not_reject_the_document(self):
        raw = (
            rb"{\rtf1\ansi\ansicpg1252\deff0"
            rb"{\pict\pngblip\picw100\pich100\picwgoal1500\pichgoal1500 "
            rb"89504e470d0a1a0a0000000d494844520000006400000064080600000070}"
            rb"\par Patient reports taking atorvastatin 20mg daily for hyperlipidemia management.\par}"
        )
        text = DocumentTextExtractor()._extract_from_rtf(raw)
        self.assertIn("atorvastatin", text)
        self.assertIn("[Embedded image not transcribed]", text)

    def test_full_page_content_image_is_marked_not_silently_dropped(self):
        html = (
            "<html><body>"
            '<img src="scan.png" width="1200" height="1600">'
            "<p>Assessment: patient stable, continue current plan.</p>"
            "</body></html>"
        )
        text = DocumentTextExtractor().extract_text(html.encode(), "text/html")
        self.assertIn("[Embedded image not transcribed]", text)
        self.assertIn("Assessment: patient stable, continue current plan.", text)

    def test_rtf_ole_object_is_still_rejected(self):
        raw = (
            rb"{\rtf1\ansi\ansicpg1252\deff0"
            rb"{\object\objdata 0105000002000000090000004d6963726f736f667420576f7264}"
            rb"\par Some plain text.\par}"
        )
        with self.assertRaises(DocumentProcessingError) as error:
            DocumentTextExtractor()._extract_from_rtf(raw)
        self.assertEqual(error.exception.code, "UNSUPPORTED_FORMAT")


class EmbeddedImageRoutingSafety(unittest.IsolatedAsyncioTestCase):
    async def test_html_never_routes_to_the_pdf_or_image_renderer(self):
        html = (
            "<html><body>"
            '<img src="scan.png" width="800" height="600">'
            "<p>Assessment: stable, no acute findings.</p>"
            "</body></html>"
        )
        with patch("src.app.services.document_ocr.extract_scanned_document", new_callable=AsyncMock) as ocr:
            text = await DocumentTextExtractor().extract_text_async(html.encode(), "text/html")
        ocr.assert_not_awaited()
        self.assertIn("Assessment: stable, no acute findings.", text)


if __name__ == "__main__":
    unittest.main()
