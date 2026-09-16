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


class OriginalEvidenceSafety(unittest.TestCase):
    def test_listed_medication_is_not_new_prescription(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        source = "Medication: Ferrous sulfate 325 mg orally once daily."
        with self.assertRaises(DocumentProcessingError):
            validate_high_risk_claims(source, {"clinical_summary": "You were prescribed ferrous sulfate to help with your condition."})
        validate_high_risk_claims(source, {"medications": ["Ferrous sulfate 325 mg orally once daily."]})

    def test_unflagged_lab_is_not_interpreted(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        source = "Ferritin: 8 ng/mL\nHemoglobin: 10.2 g/dL"
        with self.assertRaises(DocumentProcessingError):
            validate_high_risk_claims(source, {"key_insights": ["Your ferritin level was 8 ng/mL, which is low and suggests iron deficiency."]})
        validate_high_risk_claims(source, {"lab_results": ["Ferritin: 8 ng/mL", "Hemoglobin: 10.2 g/dL"]})

    def test_explicit_high_risk_source_statements_are_allowed(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        source = "Prescribed ferrous sulfate 325 mg once daily.\nFerritin: 8 ng/mL, low.\nSeen for anemia."
        validate_high_risk_claims(source, {"clinical_summary": source})

    def test_unrelated_prescription_does_not_authorize_new_medication_claim(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        with self.assertRaises(DocumentProcessingError):
            validate_high_risk_claims("Prescribed aspirin. Medication: ferrous sulfate.", {"clinical_summary": "Prescribed ferrous sulfate."})

    def test_visit_purpose_not_inferred_from_assessment(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        with self.assertRaises(DocumentProcessingError):
            validate_high_risk_claims("Assessment: Iron deficiency anemia.", {"clinical_summary": "You visited for an assessment of your health."})

class ContentIndependentGroundingSafety(unittest.TestCase):
    """Use unrelated contents to ensure checks do not recognize incident fixtures."""

    def test_prescription_guard_applies_to_arbitrary_medication_names(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        for medication in ('Metformin', 'Lisinopril', 'Synthetic agent Ω'):
            with self.subTest(medication=medication):
                source = f'Medication: {medication}.'
                validate_high_risk_claims(source, {'medications': [source]})
                with self.assertRaises(DocumentProcessingError):
                    validate_high_risk_claims(source, {'clinical_summary': f'Prescribed {medication}.'})
                explicit = f'Prescribed {medication}.'
                validate_high_risk_claims(explicit, {'clinical_summary': explicit})

    def test_numeric_interpretation_guard_does_not_depend_on_test_name(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        for name, value, unit in [('Sodium', '141', 'mmol/L'), ('TSH', '2.3', 'mIU/L'), ('Synthetic marker Ω', '17', 'arbitrary-units')]:
            with self.subTest(name=name):
                source = f'{name}: {value} {unit}.'
                validate_high_risk_claims(source, {'lab_results': [source]})
                interpreted = f'{name}: {value} {unit}, elevated.'
                with self.assertRaises(DocumentProcessingError):
                    validate_high_risk_claims(source, {'key_insights': [interpreted]})
                validate_high_risk_claims(interpreted, {'lab_results': [interpreted]})

    def test_visit_guard_uses_source_evidence_for_unrelated_conditions(self):
        from src.app.services.clinical_grounding import validate_high_risk_claims
        from src.app.services.document_extraction import DocumentProcessingError
        for condition in ('migraine', 'eczema', 'a synthetic condition Ω'):
            with self.subTest(condition=condition):
                claim = f'Seen for {condition}.'
                with self.assertRaises(DocumentProcessingError):
                    validate_high_risk_claims(f'Assessment: {condition}.', {'clinical_summary': claim})
                validate_high_risk_claims(claim, {'clinical_summary': claim})
