"""Isolation/deadline/encoding regressions against application code, no external I/O."""
import asyncio
import codecs
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
from src.app.services.document_ingestion import mark_parsed, require_parsed, process_attachments
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services import summary_runtime
from src.app.services.summary_runtime import WorkBudget, bounded_summary, model_call

FIXTURES = Path(__file__).parent.parent / 'testdata'

class RuntimeSafety(unittest.IsolatedAsyncioTestCase):
    async def test_request_logging_never_reads_or_logs_clinical_payloads(self):
        from starlette.requests import Request
        from starlette.responses import Response
        from src.app.common.middleware import request_logging
        receive=AsyncMock(side_effect=AssertionError('logging must not read the body'))
        request=Request({'type':'http','method':'POST','path':'/care-capture/attachment-summary','query_string':b'token=SECRET_QA_TOKEN','headers':[(b'authorization',b'SECRET_QA_TOKEN'),(b'x-request-id',b'SECRET_QA_TOKEN')]},receive=receive)
        with patch.object(request_logging,'logger') as log:
            response=await request_logging.RequestLoggingMiddleware(None).dispatch(request,AsyncMock(return_value=Response('SECRET_QA_TOKEN clinical content')))
        receive.assert_not_called()
        self.assertNotIn('SECRET_QA_TOKEN',str(log.mock_calls))
        self.assertNotEqual(response.headers['x-request-id'],'SECRET_QA_TOKEN')
    async def test_http_deadline_includes_dependency_wait_and_cleans_up(self):
        from src.app.common.middleware.summary_deadline import SummaryDeadlineMiddleware
        cleaned=[]; messages=[]
        async def app(scope,receive,send):
            try: await asyncio.sleep(1)
            finally: cleaned.append(True)
        async def send(message): messages.append(message)
        await SummaryDeadlineMiddleware(app,timeout_seconds=.01)({'type':'http','path':'/care-capture/attachment-summary'},AsyncMock(),send)
        self.assertEqual(messages[0]['status'],503)
        self.assertEqual(cleaned,[True])
    async def test_parser_worker_honors_parent_limits(self):
        extractor = DocumentTextExtractor(); extractor.MAX_TEXT_CHARS=10
        with self.assertRaises(DocumentProcessingError) as caught:
            await extractor.extract_text_async(b'Clinical note exceeding configured limit', 'text/plain')
        self.assertEqual(caught.exception.code,'RESOURCE_LIMIT_EXCEEDED')
    async def test_parser_worker_propagates_transport_policy(self):
        extractor = DocumentTextExtractor(transport_enabled=True)
        text = await extractor.extract_text_async((FIXTURES/'fhir_document.json').read_bytes(),'application/fhir+json')
        self.assertIn('Iron deficiency anemia',text)
        self.assertNotIn('U1lOVEh',text)
    async def test_parsed_seal_rejects_mutated_text(self):
        doc=DocumentAttachment(file_path='qa://text',content_type='text/plain',extracted_text='Ultrasound ordered.')
        mark_parsed(doc);doc.extracted_text='Ultrasound performed.'
        with self.assertRaises(DocumentProcessingError):require_parsed(doc)
    async def test_malformed_sibling_does_not_reuse_valid_path(self):
        refs=[SimpleNamespace(ehr_resource_id='qa-ref',data={'attachments':[{'filePath':'qa://valid','contentType':'text/plain','downloadStatus':'success'},None]})]
        storage=SimpleNamespace(download_document=AsyncMock(return_value=b'Ultrasound ordered.'))
        docs=await process_attachments(refs,storage,DocumentTextExtractor())
        self.assertEqual(storage.download_document.await_count,1)
        self.assertIsNone(docs[0].extraction_error)
        self.assertIsNotNone(docs[1].extraction_error)
        self.assertNotEqual(docs[0].file_path,docs[1].file_path)
    async def test_inline_base64_is_decoded_then_parsed(self):
        import base64
        refs=[SimpleNamespace(ehr_resource_id='qa-ref',data={'attachments':[{'contentType':'application/rtf','data':base64.b64encode(b'{\\rtf1 Ultrasound ordered.}').decode()}]})]
        storage=SimpleNamespace(download_document=AsyncMock(side_effect=AssertionError('not a download')))
        docs=await process_attachments(refs,storage,DocumentTextExtractor())
        self.assertEqual(docs[0].extracted_text,'Ultrasound ordered.')
        require_parsed(docs[0]);storage.download_document.assert_not_called()
    async def test_model_timeout_retries_bounded_and_reports_canonical_code(self):
        call=AsyncMock(side_effect=TimeoutError())
        with patch.object(summary_runtime.asyncio,'sleep',new=AsyncMock()):
            with self.assertRaises(DocumentProcessingError) as caught:await model_call(call)
        self.assertEqual(caught.exception.code,'MODEL_TIMEOUT')
        self.assertEqual(call.await_count,summary_runtime.MAX_TRANSIENT_RETRIES+1)
    async def test_budget_exhaustion_prevents_model_call(self):
        call=AsyncMock();token=summary_runtime._current_budget.set(WorkBudget(max_model_calls=0))
        try:
            with self.assertRaises(DocumentProcessingError):await model_call(call)
            call.assert_not_called()
        finally:summary_runtime._current_budget.reset(token)
    async def test_cancellation_is_not_retried_or_converted_to_summary(self):
        call=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):await model_call(call)
        self.assertEqual(call.await_count,1)
    async def test_admission_rejects_before_source_work(self):
        work=AsyncMock()
        class Service:
            @bounded_summary
            async def run(self,request):await work()
        with patch.object(summary_runtime,'_slots',asyncio.Semaphore(0)):
            with self.assertRaises(DocumentProcessingError) as caught:await Service().run(SimpleNamespace())
        self.assertEqual(caught.exception.code,'RESOURCE_LIMIT_EXCEEDED');work.assert_not_called()
    async def test_deadline_cancels_source_work(self):
        cleaned=[]
        class Service:
            @bounded_summary
            async def run(self,request):
                try:await asyncio.sleep(10)
                finally:cleaned.append(True)
        with self.assertRaises(DocumentProcessingError) as caught:await Service().run(SimpleNamespace(timeout_seconds=.01))
        self.assertEqual(caught.exception.code,'SUMMARY_DEADLINE_EXCEEDED');self.assertEqual(cleaned,[True])
    async def test_hidden_nested_html_never_leaks(self):
        text=DocumentTextExtractor().extract_text(b'<div hidden><div>hidden</div>still hidden</div><p>Ultrasound ordered.</p>','text/html')
        self.assertEqual(text,'Ultrasound ordered.')
    async def test_opposite_endian_bom_rejected(self):
        data=codecs.BOM_UTF16_BE+'Dose: 5 mg'.encode('utf-16-be')
        with self.assertRaises(DocumentProcessingError) as caught:DocumentTextExtractor().extract_text(data,'text/plain;charset=utf-16le')
        self.assertEqual(caught.exception.code,'ENCODING_UNRESOLVED')
    async def test_gateway_html_cannot_be_accepted_by_pdf_library(self):
        with self.assertRaises(DocumentProcessingError) as caught:DocumentTextExtractor().extract_text((FIXTURES/'gateway_error.html').read_bytes(),'application/pdf')
        self.assertEqual(caught.exception.code,'FORMAT_CONFLICT')
    async def test_wave_audio_is_not_webp(self):
        with self.assertRaises(DocumentProcessingError) as caught:DocumentTextExtractor().extract_text(b'RIFF1234WAVE'+b'\x00'*32,'audio/wav')
        self.assertEqual(caught.exception.code,'UNSUPPORTED_FORMAT')

if __name__=='__main__':unittest.main()
