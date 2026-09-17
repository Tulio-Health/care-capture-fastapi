"""Routing and access regressions. Synthetic files only; no database or AI requests."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import fitz
from fastapi import HTTPException
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError

DATA = Path(__file__).resolve().parents[1] / 'testdata' / 'routing'


from routing_fixtures import fixture_documents


class RoutingSafety(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA / "letterhead.pdf").exists():
            fixture_documents()

    async def test_logo_pdf_has_zero_vision_calls(self):
        with patch('src.app.services.document_ocr.extract_scanned_document', new_callable=AsyncMock) as ocr:
            text = await DocumentTextExtractor().extract_text_async((DATA / 'letterhead.pdf').read_bytes(), 'application/pdf; version=1.7')
        ocr.assert_not_awaited()
        self.assertEqual(text.count('ordered; not performed'), 3)

    async def test_docx_logos_preserve_native_text_and_tables_without_vision(self):
        for location in ('header', 'body', 'footer'):
            with self.subTest(location=location), patch('src.app.services.document_ocr.extract_scanned_document', new_callable=AsyncMock) as ocr:
                text = await DocumentTextExtractor().extract_text_async((DATA / f'logo_{location}.docx').read_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.assertIn('ordered; not performed', text)
                self.assertIn('Diagnosis recorded', text)
                ocr.assert_not_awaited()

    async def test_docx_clinical_image_is_contained_without_unsupported_renderer(self):
        with patch('src.app.services.document_ocr.extract_scanned_document', new_callable=AsyncMock) as ocr:
            with self.assertRaises(DocumentProcessingError) as error:
                await DocumentTextExtractor().extract_text_async((DATA / 'clinical_image.docx').read_bytes(), 'application/octet-stream')
            self.assertEqual(error.exception.code, 'UNSUPPORTED_FORMAT')
            ocr.assert_not_awaited()

    async def test_mixed_pdf_only_transcribes_scan_and_preserves_page_order(self):
        from src.app.services.document_ocr import extract_scanned_document
        transcribe = AsyncMock(return_value='Synthetic scanned evidence')
        with patch('src.app.services.document_ocr.transcribe_verified_image', transcribe), patch('src.app.core.settings.get_settings', return_value=SimpleNamespace(ENABLE_DOCUMENT_OCR=True, DOCUMENT_OCR_MODEL='mock')):
            text = await extract_scanned_document((DATA / 'mixed_scan.pdf').read_bytes(), 'application/pdf', client=object(), model='mock')
        self.assertEqual(transcribe.await_count, 1)
        self.assertEqual(text.count('ordered; not performed'), 3)
        self.assertLess(text.index('[Page 3]'), text.index('[OCR page 4]'))

    async def test_region_tiling_skips_full_page_call_and_joins_tiles(self):
        from src.app.services.document_ocr import extract_scanned_document
        transcribe = AsyncMock(side_effect=['Tile-1-text', 'Tile-2-text'])
        with patch('src.app.services.document_ocr.transcribe_verified_image', transcribe), \
             patch('src.app.services.ocr_regions.overlapping_regions', return_value=['crop-a', 'crop-b']), \
             patch('src.app.core.settings.get_settings', return_value=SimpleNamespace(ENABLE_DOCUMENT_OCR=True, DOCUMENT_OCR_MODEL='mock')):
            text = await extract_scanned_document((DATA / 'mixed_scan.pdf').read_bytes(), 'application/pdf', client=object(), model='mock')
        # Tiling replaces the full-page call entirely: only the two crops are transcribed.
        self.assertEqual(transcribe.await_count, 2)
        self.assertTrue(all(call.kwargs.get('region') is True for call in transcribe.await_args_list))
        self.assertIn('Tile-1-text', text)
        self.assertIn('Tile-2-text', text)

    def test_blank_page_does_not_trigger_ocr_but_body_image_does(self):
        pdf = fitz.open(); pdf.new_page()
        with self.assertRaises(DocumentProcessingError) as error:
            DocumentTextExtractor().extract_text(pdf.tobytes(), 'application/pdf')
        self.assertEqual(error.exception.code, 'NO_READABLE_TEXT')
        pdf.close()
        # Readable native text must not hide an additional clinical image in the body.
        import io
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (100, 100), 'white').save(stream, format='PNG')
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((36, 40), 'Referral ordered; not performed.')
        page.insert_image(fitz.Rect(36, 120, 400, 600), stream=stream.getvalue())
        with self.assertRaises(DocumentProcessingError) as error:
            DocumentTextExtractor().extract_text(pdf.tobytes(), 'application/pdf')
        self.assertEqual(error.exception.code, 'OCR_REQUIRED')
        pdf.close()


class AccessCompatibilitySafety(unittest.IsolatedAsyncioTestCase):
    async def test_trusted_service_delegation_requires_no_patient_mapping_but_requires_appointment_ownership(self):
        from src.app.services.summary_authorization import authorize_summary_scope
        appointment_id = 'appointment-id'
        for scope in ('service', 'patient-id', None):
            with self.subTest(scope=scope):
                request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(summary_ready=True)), state=SimpleNamespace(user={'is_authenticated': True, 'is_internal_service': True, 'clerk_id': scope}))
                session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: appointment_id)))
                await authorize_summary_scope(request, 'patient-id', session, appointment_id)
                # No patient-identity mapping lookup is needed for a trusted service - but the
                # appointment ownership lookup (against appointments, not users) is mandatory.
                session.execute.assert_awaited_once()
                executed_sql = str(session.execute.await_args.args[0]).lower()
                self.assertIn('appointments', executed_sql)
                self.assertNotIn('users', executed_sql)

        # An appointment that doesn't belong to the claimed patient is rejected even for a
        # trusted-service call with no patient-scope header.
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(summary_ready=True)), state=SimpleNamespace(user={'is_authenticated': True, 'is_internal_service': True, 'clerk_id': None}))
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, 'patient-id', session, appointment_id)
        self.assertEqual(error.exception.status_code, 403)

    async def test_authenticated_patient_access_and_cross_patient_rejection(self):
        from src.app.services.summary_authorization import authorize_summary_scope
        appointment_id = 'appointment-id'
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(summary_ready=True)), state=SimpleNamespace(user={'is_authenticated': True, 'clerk_id': 'clerk-patient'}))

        # Self-access with an appointment that belongs to the patient: allowed.
        session = SimpleNamespace(execute=AsyncMock(side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: 'patient-id'),
            SimpleNamespace(scalar_one_or_none=lambda: appointment_id),
        ]))
        await authorize_summary_scope(request, 'patient-id', session, appointment_id)

        # Cross-patient request: the caller's own identity maps to an unrelated patient, so
        # delegation checks run and fail before any appointment lookup happens.
        session = SimpleNamespace(execute=AsyncMock(side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: 'patient-id'),
            SimpleNamespace(scalar_one_or_none=lambda: None),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, 'different-patient', session, appointment_id)
        self.assertEqual(error.exception.status_code, 403)

        # Self-access, but the named appointment belongs to someone else: rejected.
        session = SimpleNamespace(execute=AsyncMock(side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: 'patient-id'),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, 'patient-id', session, appointment_id)
        self.assertEqual(error.exception.status_code, 403)
