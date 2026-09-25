"""Count production grounding calls with fake model boundaries; no paid API or DB."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from src.app.chains.attachment_summarization import chain as chain_module
from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain, _deferred_grounding, _create_batches
from src.app.models.attachment_summarization import DocumentAttachment, DocumentSummary, AttachmentSummarizationResponse
from src.app.services.document_ingestion import mark_parsed
from src.app.services.clinical_grounding import GroundingFit
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.validated_summary import require_validated_summary


def inputs(identity='source-a', text='Cough documented. Rest advised.'):
    document=DocumentAttachment(file_path='qa://'+identity, content_type='text/plain',resource_id=identity,extracted_text=text)
    mark_parsed(document)
    extraction=DocumentSummary(source_document_id=_create_batches([document])[0][0].resource_id,source_document_title=identity,source_document_type='Visit note',evidence_quotes=[text],narrative_summary=text)
    output=AttachmentSummarizationResponse(clinical_summary=text,documents_analyzed=1)
    return document,extraction,output


def chain_for(extraction,output):
    chain=AttachmentSummarizationChain();chain._model=object()
    chain._extraction_agent=NS(run=AsyncMock(return_value=NS(output=[extraction])))
    chain._synthesis_agent=NS(run=AsyncMock(return_value=NS(output=output)))
    return chain


class GroundingCostSafety(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_summary_has_two_generations_and_one_original_source_audit(self):
        doc,extraction,output=inputs();chain=chain_for(extraction,output)
        with patch('src.app.chains.attachment_summarization.chain.verify_grounding',new_callable=AsyncMock) as audit:
            result=await chain.analyze({},[doc])
        self.assertEqual(chain.extraction_agent.run.await_count,1)
        self.assertEqual(chain.synthesis_agent.run.await_count,1)
        audit.assert_awaited_once()
        self.assertEqual(audit.call_args.args[1],doc.extracted_text)
        self.assertNotIn('validated_source_records',audit.call_args.args[1])
        require_validated_summary(result)
        self.assertIsNone(_deferred_grounding.get())

    async def test_rejected_final_candidate_is_never_sealed(self):
        doc,extraction,output=inputs();chain=chain_for(extraction,output)
        with patch('src.app.chains.attachment_summarization.chain.verify_grounding',new_callable=AsyncMock,side_effect=DocumentProcessingError('GROUNDING_VALIDATION_FAILED')) as audit,patch('src.app.services.validated_summary.seal_summary') as seal:
            with self.assertRaises(DocumentProcessingError):await chain.analyze({},[doc])
        seal.assert_not_called()
        # Bound, not a pin: 3 awaits at HEAD (single audit + 2 staged replays); up to 5 once
        # the replay retry lands -- 2*(len(batches)+1)+1 with batches=1. The safety invariant
        # is seal_not_called + the raise, which stay exact.
        self.assertGreaterEqual(audit.await_count,1)
        self.assertLessEqual(audit.await_count,5)
        self.assertIsNone(_deferred_grounding.get())

    async def test_unsupported_source_quote_fails_before_paid_audit_or_synthesis(self):
        doc,extraction,output=inputs();extraction.evidence_quotes=['Invented quotation']
        chain=chain_for(extraction,output)
        with patch('src.app.chains.attachment_summarization.chain.verify_grounding',new_callable=AsyncMock) as audit:
            with self.assertRaises(DocumentProcessingError):await chain.analyze({},[doc])
        audit.assert_not_awaited();chain.synthesis_agent.run.assert_not_awaited()

    def _force_single_audit_oversized(self,output):
        # Step 2 (round9-revision.md section 4.4(c)): GROUNDING_MAX_CHARACTERS is deleted, and
        # both the single-candidate check (site 4) and the per-snapshot replay checks (site 3)
        # now share the one grounding_request_fits predicate -- there is no longer a separate
        # knob that forces "oversized" for only one of them. Preserve this test's real intent
        # (force the SINGLE whole-candidate audit's oversized entrance, while leaving the
        # per-snapshot replay checks real so the staged replay this test targets actually runs
        # real judges) by discriminating on object identity: chain._verify_final's own call
        # passes the exact final `output` object built by inputs() below; every per-snapshot
        # replay call in _audit_once_retried passes a *copy* (chain.py's _verify_stage does
        # `candidate.model_copy(deep=True)` before appending to `audits`), so `is output` is
        # true only at the single-audit call site.
        real_fits=chain_module.grounding_request_fits
        def forced(source,candidate,**kwargs):
            if candidate is output:
                return GroundingFit(fits=False,reason='call_byte_ceiling',body_bytes=999_999)
            return real_fits(source,candidate,**kwargs)
        return forced

    async def test_large_input_falls_back_to_original_staged_audits_without_truncation(self):
        doc,extraction,output=inputs();chain_instance=chain_for(extraction,output)
        with patch('src.app.chains.attachment_summarization.chain.grounding_request_fits',side_effect=self._force_single_audit_oversized(output)),patch('src.app.chains.attachment_summarization.chain.verify_grounding',new_callable=AsyncMock) as audit:
            await chain_instance.analyze({},[doc])
        self.assertEqual(audit.await_count,2)
        self.assertEqual(audit.call_args_list[0].args[1],doc.extracted_text)
        self.assertIn('validated_source_records',audit.call_args_list[1].args[1])

    async def test_large_input_fallback_rejection_cannot_publish(self):
        doc,extraction,output=inputs();chain_instance=chain_for(extraction,output)
        with patch('src.app.chains.attachment_summarization.chain.grounding_request_fits',side_effect=self._force_single_audit_oversized(output)),patch('src.app.chains.attachment_summarization.chain.verify_grounding',new_callable=AsyncMock,side_effect=DocumentProcessingError('GROUNDING_VALIDATION_FAILED')),patch('src.app.services.validated_summary.seal_summary') as seal:
            with self.assertRaises(DocumentProcessingError):await chain_instance.analyze({},[doc])
        seal.assert_not_called()

    async def test_concurrent_requests_do_not_share_evidence(self):
        first=inputs('first','Cough documented.');second=inputs('second','Headache documented.')
        chains=[chain_for(x[1],x[2]) for x in [first,second]]
        seen=[]
        async def audit(model,source,candidate):
            await asyncio.sleep(0)
            seen.append((source,candidate.clinical_summary))
        with patch('src.app.chains.attachment_summarization.chain.verify_grounding',side_effect=audit):
            await asyncio.gather(*(chain.analyze({},[items[0]]) for chain,items in zip(chains,[first,second])))
        self.assertCountEqual(seen,[('Cough documented.','Cough documented.'),('Headache documented.','Headache documented.')])
        self.assertIsNone(_deferred_grounding.get())

if __name__=='__main__':unittest.main()
