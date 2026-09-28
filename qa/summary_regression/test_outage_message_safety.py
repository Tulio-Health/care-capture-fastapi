"""Outage outcomes use the existing summary contract. Memory-only publication."""
from types import SimpleNamespace
import unittest
from uuid import uuid4
from src.app.services.summary_outcomes import MESSAGES, nonclinical_payload, unavailable_message
from src.app.models.conversation_summaries import ConversationSummary
from test_publication_safety import setup_repository, payload


class OutageSafety(unittest.IsolatedAsyncioTestCase):
    def test_dependency_failures_return_safe_message_without_clinical_fields(self):
        request=SimpleNamespace(user_id=uuid4())
        for code in ('MODEL_UNAVAILABLE','MODEL_TIMEOUT','MODEL_RATE_LIMITED','MODEL_AUTH_FAILED','OCR_TIMEOUT'):
            result=nonclinical_payload(request,'attachment_summary',errors=[{'error':code,'detail':'provider-secret'}])
            self.assertEqual(result['summary_text'],MESSAGES['service_unavailable'])
            self.assertEqual(result['summary_metadata']['processing_outcome'],'unavailable')
            self.assertFalse(result['summary_metadata']['is_clinical_summary'])
            for field in ('key_points','medications','diagnoses','instructions','recommendations'):self.assertEqual(result[field],[])
            self.assertNotIn('provider-secret',str(result))

    def test_format_and_empty_document_messages_remain_distinct(self):
        self.assertEqual(unavailable_message([{'error':'UNSUPPORTED_FORMAT'}]),MESSAGES['unsupported'])
        self.assertEqual(unavailable_message([{'error':'PARSE_FAILED'}]),MESSAGES['unavailable'])
        request=SimpleNamespace(user_id=uuid4())
        self.assertEqual(nonclinical_payload(request,'attachment_summary',state='no_documents')['summary_text'],MESSAGES['no_documents'])

    async def test_outage_preserves_previous_valid_summary_and_refresh_notice(self):
        request=SimpleNamespace(user_id=uuid4(),appointment_id=uuid4())
        repository,session=setup_repository()
        row=await repository.upsert(request.appointment_id,payload(request))
        previous=row.diagnoses
        failed=nonclinical_payload(request,'attachment_summary',errors=[{'error':'MODEL_UNAVAILABLE'}])
        for _ in range(2):await repository.upsert(request.appointment_id,failed)
        self.assertEqual(row.diagnoses,previous)
        self.assertEqual(row.summary_text.count('previous summary'),1)
        self.assertIn('Ultrasound ordered; not performed.',row.summary_text)
        self.assertEqual(len(session.rows),1)
        self.assertEqual(row.summary_metadata['last_refresh_outcome']['processing_errors'][0]['error'],'MODEL_UNAVAILABLE')

    def test_attachment_payload_serializes_outage_in_existing_mobile_summary_field(self):
        from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService
        from src.app.models.attachment_summarization import AttachmentSummarizationRequest, AttachmentSummarizationResponse
        from datetime import datetime,timezone
        request=AttachmentSummarizationRequest(user_id=uuid4(),appointment_id=uuid4())
        appointment=SimpleNamespace(appointment_date=None,purpose=None,ehr_entity_id='qa')
        result=AttachmentSummarizationResponse(clinical_summary='',documents_analyzed=0,extraction_errors=[{'error':'MODEL_UNAVAILABLE'}])
        data=AttachmentSummarizationService._prepare_summary_data(None,request,appointment,'N/A',result,[])
        wire=ConversationSummary.model_validate({**data,'id':uuid4(),'appointment_id':request.appointment_id,'created_at':datetime.now(timezone.utc),'updated_at':datetime.now(timezone.utc)}).model_dump(mode='json',by_alias=True)
        self.assertEqual(wire['summaryText'],MESSAGES['service_unavailable'])
        self.assertEqual(data['summary_metadata']['processing_outcome'],'unavailable')

if __name__=='__main__':unittest.main()
