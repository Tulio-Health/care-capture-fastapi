"""Regressions for defects exposed while enabling previously blocked cases."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

DATA=Path(__file__).parent.parent/'testdata'

class FollowupSafety(unittest.IsolatedAsyncioTestCase):
    async def test_long_procedure_document_reaches_tail_without_truncation(self):
        from src.app.chains.procedure_extraction.chain import ProcedureExtractionChain
        from src.app.models.attachment_summarization import DocumentAttachment
        from src.app.models.procedure_summarization import ProcedureDocumentExtraction
        from src.app.services.document_ingestion import mark_parsed
        document=mark_parsed(DocumentAttachment(file_path='qa://long',content_type='text/plain',resource_id='long',extracted_text=(DATA/'long_middle_late.txt').read_text()))
        received=[]
        async def respond(prompt,*,deps):
            received.append(deps)
            return SimpleNamespace(output=ProcedureDocumentExtraction(procedures=[],evidence_quotes=[]))
        chain=ProcedureExtractionChain();chain._model=object();chain._agent=SimpleNamespace(run=AsyncMock(side_effect=respond))
        with patch('src.app.chains.procedure_extraction.chain.verify_grounding',new=AsyncMock()):
            events,failures=await chain.extract([document])
        self.assertFalse(failures);self.assertFalse(events)
        self.assertGreater(len(received),1)
        self.assertIn('Repeat CBC in 2 weeks',''.join(received))
        self.assertTrue(all(len(part)<=48000 for part in received))
        self.assertEqual(received[0][:100],document.extracted_text[:100])
        self.assertTrue(document.extracted_text.endswith(received[-1]))

    async def test_failed_procedure_chunk_fails_whole_document(self):
        from src.app.chains.procedure_extraction.chain import ProcedureExtractionChain
        from src.app.models.attachment_summarization import DocumentAttachment
        from src.app.models.procedure_summarization import ProcedureDocumentExtraction
        from src.app.services.document_ingestion import mark_parsed
        from src.app.services.document_extraction import DocumentProcessingError
        document=mark_parsed(DocumentAttachment(file_path='qa://long',content_type='text/plain',resource_id='long',extracted_text=(DATA/'long_middle_late.txt').read_text()))
        response=SimpleNamespace(output=ProcedureDocumentExtraction(procedures=[],evidence_quotes=[]))
        chain=ProcedureExtractionChain();chain._model=object();chain._agent=SimpleNamespace(run=AsyncMock(side_effect=[response,DocumentProcessingError('MODEL_TIMEOUT')]))
        with patch('src.app.chains.procedure_extraction.chain.verify_grounding',new=AsyncMock()):
            events,failures=await chain.extract([document])
        self.assertEqual(events,[])
        self.assertEqual(failures,[{'source_id':'long','error':'MODEL_TIMEOUT'}])

    async def test_bad_translation_preserves_original_with_visible_notice(self):
        from translation_adapter import run
        for case_id in ['A07-SCALARS','A07-PROSE','A07-ARRAY','A07-TYPE','A07-EMPTY']:
            observed=await run({'id':case_id},DATA)
            self.assertFalse(observed['translation']['accepted'])
            self.assertTrue(observed['translation']['original_preserved'])
            self.assertTrue(observed['translation']['limitation_disclosed'])

    async def test_unknown_classification_body_cannot_be_silently_accepted(self):
        from pydantic import ValidationError
        from src.app.models.document_type_inference import DocumentTypeInferenceRequest
        with self.assertRaises(ValidationError):
            DocumentTypeInferenceRequest(id='qa',document_body=(DATA/'clinical.rtf').read_text())


# PR-12b: OriginalEvidenceSafety and ContentIndependentGroundingSafety (both testing
# validate_high_risk_claims directly) were removed -- that classifier is deleted entirely (see
# clinical_grounding.py and test_clinical_grounding.py for its replacement coverage: the LLM
# judge now runs unconditionally on this content instead).
