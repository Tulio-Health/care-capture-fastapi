"""Evidence inconsistencies trigger bounded rechecks, never automatic approval."""
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ocr import OCRVerification, verification_is_consistent, transcribe_verified_image
from src.app.services.clinical_grounding import validate_high_risk_claims
from src.app.services.summary_runtime import WorkBudget, _current_budget
from test_ocr_verification_safety import response

TEXT='Mixtard x2\nMixtard x1'

def issue(**changes):
    values=dict(kind='text_mismatch',region='second medication block',candidate_line=2,candidate_quote='Mixtard x2',source_quote='Mixtard x1',reason='Different quantity')
    values.update(changes)
    return values

def verdict(**changes):
    values=dict(matches=False,issues=[issue()]);values.update(changes)
    return response(json.dumps(values))

class EvidenceSafety(unittest.IsolatedAsyncioTestCase):
    def client(self,*checks):
        create=AsyncMock(side_effect=[response(json.dumps(dict(text=TEXT,complete=True,unreadable_regions=[]))),*checks])
        return NS(chat=NS(completions=NS(create=create))),create

    async def test_wrong_line_quote_rechecked_not_autoapproved(self):
        client,create=self.client(verdict(),verdict(matches=True,issues=[]))
        self.assertEqual(await transcribe_verified_image(client,'mock','image',1),TEXT)
        self.assertEqual(create.await_count,3)
        self.assertEqual(create.call_args_list[1].kwargs['messages'][1],create.call_args_list[2].kwargs['messages'][1])

    async def test_repeated_contradiction_fails_closed(self):
        client,create=self.client(verdict(),verdict())
        with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        self.assertEqual(create.await_count,3)

    async def test_recheck_confirming_genuine_mismatch_withholds_text(self):
        genuine=verdict(issues=[issue(candidate_quote='Mixtard x1',source_quote='Mixtard x2')])
        client,create=self.client(verdict(),genuine)
        with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        self.assertEqual(create.await_count,3)

    async def test_genuine_mismatch_is_not_retried(self):
        client,create=self.client(verdict(issues=[issue(candidate_quote='Mixtard x1',source_quote='Mixtard x2')]))
        with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        self.assertEqual(create.await_count,2)

    async def test_truncation_and_inconsistency_share_one_retry(self):
        client,create=self.client(response('{}','length'),verdict())
        with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        self.assertEqual(create.await_count,3)

    async def test_inconsistent_verdict_cannot_exceed_job_budget(self):
        client,create=self.client(verdict(),verdict(matches=True,issues=[]))
        token=_current_budget.set(WorkBudget(max_model_calls=2))
        try:
            with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        finally:_current_budget.reset(token)
        self.assertEqual(create.await_count,2)

    def test_equal_quotes_and_unanchored_evidence_are_inconclusive(self):
        for value in [issue(candidate_quote='Mixtard x1'),issue(candidate_line=99),issue(candidate_quote='invented'),issue(candidate_line=0),issue(candidate_line=None)]:
            self.assertFalse(verification_is_consistent(OCRVerification(matches=False,issues=[value]),TEXT))
        self.assertFalse(verification_is_consistent(OCRVerification(matches=False,issues=[]),TEXT))
        self.assertFalse(verification_is_consistent(OCRVerification(matches=True,issues=[issue()]),TEXT))

    def test_explicit_omission_or_uncertainty_remains_rejection(self):
        for value in [issue(kind='missing_text',candidate_line=None,candidate_quote=None,source_quote='Missing plan'),issue(kind='unreadable',candidate_line=None,candidate_quote=None,source_quote=None)]:
            v=OCRVerification(matches=False,issues=[value]);self.assertTrue(verification_is_consistent(v,TEXT));self.assertFalse(v.matches)

class SynthesisSafety(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_lab_interpretation_is_regenerated_and_revalidated(self):
        from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
        from src.app.models.attachment_summarization import AttachmentSummarizationResponse
        records=[{'lab_results':['Hemoglobin: 13.5 g/dL. Reference range: 12.0-16.0 g/dL.']}]
        bad=AttachmentSummarizationResponse(clinical_summary='Your hemoglobin 13.5 g/dL is normal.',documents_analyzed=1)
        good=AttachmentSummarizationResponse(clinical_summary='The record contains laboratory results.',documents_analyzed=1)
        run=AsyncMock(side_effect=[NS(output=bad),NS(output=good)])
        chain=AttachmentSummarizationChain();chain._model=object();chain._synthesis_agent=NS(run=run)
        async def verify(model,source,output):validate_high_risk_claims(source,output)
        with patch('src.app.chains.attachment_summarization.chain.verify_grounding',side_effect=verify):
            result=await chain._synthesize_records({},records,1)
        self.assertEqual(run.await_count,2)
        self.assertEqual(result.lab_results,records[0]['lab_results'])
        self.assertNotIn('normal',result.clinical_summary)

    async def test_repeated_unsupported_summary_is_withheld(self):
        from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
        chain=AttachmentSummarizationChain()
        failure=DocumentProcessingError('GROUNDING_VALIDATION_FAILED')
        with patch.object(chain,'_synthesize_records_attempt',side_effect=failure) as attempt:
            with self.assertRaises(DocumentProcessingError):await chain._synthesize_records({},[],1)
        self.assertEqual(attempt.await_count,2)

    async def test_capacity_failure_never_triggers_synthesis_repair(self):
        from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
        chain=AttachmentSummarizationChain()
        with patch.object(chain,'_synthesize_records_attempt',side_effect=DocumentProcessingError('RESOURCE_LIMIT_EXCEEDED')) as attempt:
            with self.assertRaises(DocumentProcessingError):await chain._synthesize_records({},[],1)
        self.assertEqual(attempt.await_count,1)

    async def test_verifier_receives_actual_final_summary_fields(self):
        from src.app.services.clinical_grounding import verify_grounding,GroundingVerdict
        from src.app.models.attachment_summarization import AttachmentSummarizationResponse
        candidate=AttachmentSummarizationResponse(clinical_summary='Chest X-ray ordered. Not performed.',recommendations=['Chest X-ray ordered. Not performed.'],documents_analyzed=1)
        run=AsyncMock(return_value=NS(output=GroundingVerdict(supported=True,issues=[])))
        with patch('src.app.core.settings.get_settings',return_value=NS(DOCUMENT_VERIFICATION_MODEL='mock')),patch('src.app.common.llm_factory.get_pydantic_ai_model',return_value=object()),patch('pydantic_ai.Agent',return_value=NS(run=run)) as agent:
            await verify_grounding(None,'Chest X-ray ordered. Not performed.',candidate)
        payload=json.loads(run.call_args.args[0])
        self.assertEqual(payload['candidate_fields'],sorted(candidate.model_dump()))
        self.assertNotIn('procedures_ordered',payload['candidate_fields'])
        self.assertIn('This final summary schema has NO procedures_ordered field',agent.call_args.kwargs['system_prompt'])

if __name__=='__main__':unittest.main()
