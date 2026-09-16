"""Content-independent coverage of the approved release policy and new safety edges."""
import asyncio
import base64
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from src.app.services.document_extraction import DocumentProcessingError, DocumentTextExtractor

DATA=Path(__file__).resolve().parents[1]/'testdata'

class ReleasePolicySafety(unittest.TestCase):
    def test_fhir_and_multipart_work_without_environment_switches(self):
        for name,mime in [('fhir_document.json','application/fhir+json; charset=UTF-8'),('fhir_document.xml','application/fhir+xml'),('multipart.eml','multipart/mixed')]:
            path=DATA/name
            self.assertTrue(path.is_file())
            with self.subTest(name=name):
                self.assertIn('Iron deficiency anemia',DocumentTextExtractor().extract_text(path.read_bytes(),mime))

    def test_unsupported_optional_formats_cannot_be_enabled_by_old_switch(self):
        for name,mime in [('clinical.txt.gz','application/gzip'),('export.zip','application/zip'),('clinical_utf8.txt','application/fhir+ndjson')]:
            path=DATA/name
            content=path.read_bytes() if path.exists() else b'PK\x03\x04invalid'
            with self.subTest(mime=mime),self.assertRaises(DocumentProcessingError) as failure:
                DocumentTextExtractor(transport_enabled=True,allow_containers=True).extract_text(content,mime)
            self.assertEqual(failure.exception.code,'UNSUPPORTED_FORMAT')

    def test_stored_s3_paths_do_not_require_per_user_prefix_configuration(self):
        from src.app.utils.s3_client import S3DocumentClient
        client=S3DocumentClient()
        for key in ('users/alice/file.pdf','connections/random/other-user/file.rtf'):
            self.assertEqual(client.authorize_location('s3://synthetic-bucket/'+key),('synthetic-bucket',key))
        self.assertIsNone(client._s3_client)  # Pure validation; no credentials or AWS calls.
        with self.assertRaises(ValueError):
            client.authorize_location('s3://synthetic-bucket/file.pdf\n')
        with self.assertRaises(DocumentProcessingError):
            S3DocumentClient(allowed_prefixes=['s3://synthetic-bucket/users/alice/']).authorize_location('s3://synthetic-bucket/users/alice-other/file.pdf')

    def test_region_checks_do_not_remove_legitimate_repeated_rows(self):
        from src.app.services.ocr_regions import validate_region_coverage
        source='Heading\nSame recorded result\nSame recorded result\nFooter'
        self.assertEqual(validate_region_coverage(source,['Heading\nSame recorded result\nSame recorded result']),source)
        with self.assertRaises(DocumentProcessingError):
            validate_region_coverage(source,['Heading\nDifferent recorded result\nFooter'])

    def test_region_images_overlap_and_cover_bottom_of_page(self):
        from PIL import Image
        from src.app.services.ocr_regions import overlapping_regions
        image=Image.new('RGB',(10,2500),'white')
        stream=io.BytesIO();image.save(stream,format='PNG')
        regions=overlapping_regions(base64.b64encode(stream.getvalue()).decode())
        sizes=[Image.open(io.BytesIO(base64.b64decode(region))).size for region in regions]
        self.assertEqual(sizes,[(10,2200),(10,540)])

class LegacyAndFallbackSafety(unittest.IsolatedAsyncioTestCase):
    async def test_real_legacy_word_parser_preserves_order_status(self):
        text=await DocumentTextExtractor().extract_text_async((DATA/'legacy_word.doc').read_bytes(),'application/msword')
        self.assertIn('ordered; not performed',text)
        self.assertNotIn('\\rtf',text)

    async def test_fallback_error_preserves_contained_attachment_outcome(self):
        from src.app.services.summarization.comprehensive_summarization import ComprehensiveSummarizationService
        service=object.__new__(ComprehensiveSummarizationService)
        original=SimpleNamespace(metadata={'processing_outcome':'unavailable','processing_errors':[{'error':'PARSE_FAILED'}]})
        service._run_attachment_summarization=AsyncMock(return_value=original)
        service._run_fhir_analysis=AsyncMock(side_effect=RuntimeError('synthetic failure'))
        self.assertIs(await service._run_attachment_with_fhir_fallback(object()),original)

    async def test_valid_previous_summary_is_not_replaced_by_fallback(self):
        from src.app.services.summarization.comprehensive_summarization import ComprehensiveSummarizationService
        service=object.__new__(ComprehensiveSummarizationService)
        previous=SimpleNamespace(metadata={'is_clinical_summary':True,'last_refresh_outcome':{'processing_outcome':'unavailable'}})
        service._run_attachment_summarization=AsyncMock(return_value=previous)
        service._run_fhir_analysis=AsyncMock()
        self.assertIs(await service._run_attachment_with_fhir_fallback(object()),previous)
        service._run_fhir_analysis.assert_not_called()

    async def test_auth_failure_is_not_misclassified_as_prior_ocr_routing_exception(self):
        from src.app.services.summary_runtime import model_call
        class ProviderAuthenticationError(Exception):
            status_code=401
        operation=AsyncMock(side_effect=ProviderAuthenticationError('synthetic credential rejection'))
        try:
            raise DocumentProcessingError('OCR_REQUIRED')
        except DocumentProcessingError:
            with self.assertRaises(DocumentProcessingError) as failure:
                await model_call(operation)
        self.assertEqual(failure.exception.code,'MODEL_AUTH_FAILED')
        self.assertEqual(operation.await_count,1)

class NestedFHIRSafety(unittest.TestCase):
    def test_json_and_xml_bundles_parse_children(self):
        import json
        note='Ultrasound ordered; not performed.'
        encoded=base64.b64encode(note.encode()).decode()
        bundle={'resourceType':'Bundle','entry':[{'resource':{'resourceType':'Binary','contentType':'text/plain','data':encoded}}]}
        xml=f'<Bundle xmlns="http://hl7.org/fhir"><entry><resource><Binary><contentType value="text/plain"/><data value="{encoded}"/></Binary></resource></entry></Bundle>'
        for content,mime in [(json.dumps(bundle),'application/fhir+json'),(xml,'application/fhir+xml')]:
            result=DocumentTextExtractor().extract_text(content.encode(),mime)
            self.assertIn(note,result);self.assertNotIn(encoded,result)

    def test_nested_report_attachment_is_parsed_in_both_encodings(self):
        import json
        note=b'{\\rtf1 Follow-up scheduled; not completed.}'
        encoded=base64.b64encode(note).decode()
        report={'resourceType':'DiagnosticReport','presentedForm':[{'contentType':'application/rtf','data':encoded}]}
        xml=f'<DiagnosticReport xmlns="http://hl7.org/fhir"><presentedForm><contentType value="text/rtf"/><data value="{encoded}"/></presentedForm></DiagnosticReport>'
        for content,mime in [(json.dumps(report),'application/fhir+json'),(xml,'application/fhir+xml')]:
            result=DocumentTextExtractor().extract_text(content.encode(),mime)
            self.assertIn('not completed',result);self.assertNotIn(encoded,result);self.assertNotIn('\\rtf',result)

    def test_nested_attachment_cannot_trigger_external_fetch_or_hide_failed_parse(self):
        import json
        for attachment in [{'contentType':'text/plain','url':'https://example.invalid/clinical'}, {'contentType':'application/pdf','data':base64.b64encode(b'not a PDF').decode()}]:
            with self.assertRaises(DocumentProcessingError):
                DocumentTextExtractor().extract_text(json.dumps({'resourceType':'DiagnosticReport','presentedForm':[attachment]}).encode(),'application/fhir+json')

    def test_bundle_entry_limit_is_enforced_before_children_are_parsed(self):
        import json
        extractor=DocumentTextExtractor();extractor.MAX_ZIP_ENTRIES=1
        with self.assertRaises(DocumentProcessingError) as failure:
            extractor.extract_text(json.dumps({'resourceType':'Bundle','entry':[{'resource':{'resourceType':'Condition'}},{'resource':{'resourceType':'Condition'}}]}).encode(),'application/fhir+json')
        self.assertEqual(failure.exception.code,'RESOURCE_LIMIT_EXCEEDED')

    def test_typed_attachment_without_mime_is_sniffed_not_forwarded(self):
        import json
        raw=b'{\\rtf1 Procedure ordered; not performed.}'
        encoded=base64.b64encode(raw).decode()
        for content,mime in [(json.dumps({'resourceType':'Observation','valueAttachment':{'data':encoded}}),'application/fhir+json'),(f'<DiagnosticReport><presentedForm><data value="{encoded}"/></presentedForm></DiagnosticReport>','application/fhir+xml')]:
            text=DocumentTextExtractor().extract_text(content.encode(),mime)
            self.assertIn('not performed',text);self.assertNotIn(encoded,text);self.assertNotIn('\\rtf',text)

class ParserCleanupSafety(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_worker_removes_parent_owned_source_workspace(self):
        import json
        import sys
        from unittest.mock import patch
        original=asyncio.create_subprocess_exec
        workspaces=[]
        processes=[]
        async def spawn(*args,**kwargs):
            workspace=json.loads(args[-1])['workspace']
            workspaces.append(Path(workspace))
            script='from pathlib import Path; import sys,time; Path(sys.argv[1],"source.doc").write_text("synthetic private source"); time.sleep(30)'
            process=await original(sys.executable,'-c',script,workspace,**kwargs)
            processes.append(process)
            return process
        with patch('src.app.services.document_extraction.asyncio.create_subprocess_exec',side_effect=spawn):
            task=asyncio.create_task(DocumentTextExtractor().extract_text_async(b'synthetic','text/plain'))
            try:
                for _ in range(200):
                    if workspaces and (workspaces[0]/'source.doc').exists():break
                    await asyncio.sleep(.01)
                self.assertTrue(workspaces and (workspaces[0]/'source.doc').exists())
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(workspaces[0].exists())
        self.assertIsNotNone(processes[0].returncode)
