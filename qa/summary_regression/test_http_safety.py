"""Real FastAPI route serialization with dependency boundaries mocked, no database."""
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from src.app.models.conversation_summaries import ConversationSummary
from src.app.services.summary_outcomes import nonclinical_payload
from src.app.services.document_extraction import DocumentProcessingError
from run_pack import no_network

class HttpSafety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack=ExitStack();self.stack.enter_context(no_network())
        from src.app.routes import care_capture
        self.routes=care_capture
        self.app=FastAPI();self.app.state.summary_ready=True
        self.app.include_router(care_capture.router)
        # Ownership-capable stub: the route's authorize_summary_scope unconditionally
        # verifies appointment ownership (appointment_belongs_to -> session.execute), so the
        # stub must answer that one query; route + serialization stay fully real.
        appointment_id_holder=self
        class _OwnershipDb:
            async def execute(self,*_a,**_k):
                return SimpleNamespace(scalar_one_or_none=lambda:appointment_id_holder.request.appointment_id)
        async def no_database():yield _OwnershipDb()
        self.app.dependency_overrides[care_capture.get_db]=no_database
        @self.app.middleware('http')
        async def trusted_request(request,call_next):
            request.state.user={'is_authenticated':True,'is_internal_service':True,'clerk_id':'service'}
            return await call_next(request)
        self.identity=uuid4();self.request=SimpleNamespace(user_id=self.identity,appointment_id=uuid4())
        self.body={'user_id':str(self.identity),'appointment_id':str(self.request.appointment_id)}
        settings=SimpleNamespace(ENABLE_DOCUMENT_TRANSPORT=False,ENABLE_DOCUMENT_CONTAINERS=False)
        self.stack.enter_context(patch('src.app.core.settings.get_settings',return_value=settings))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://qa')
    async def asyncTearDown(self):
        await self.client.aclose();self.stack.close()
    async def test_failure_message_uses_existing_mobile_json_aliases(self):
        data=nonclinical_payload(self.request,'attachment_summary')
        data.update(id=uuid4(),appointment_id=self.request.appointment_id,created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))
        model=ConversationSummary.model_validate(data)
        with patch.object(self.routes.AttachmentSummarizationService,'analyze_attachments',new=AsyncMock(return_value=model)):
            response=await self.client.post('/care-capture/attachment-summary',json=self.body)
        self.assertEqual(response.status_code,200)
        wire=response.json();self.assertEqual(wire['summaryText'],data['summary_text'])
        self.assertEqual(wire['summaryMetadata']['processing_outcome'],'unavailable')
        self.assertEqual(wire['diagnoses'],[]);self.assertNotIn('summary_text',wire)
    async def test_unexpected_provider_error_is_not_exposed(self):
        with patch.object(self.routes.AttachmentSummarizationService,'analyze_attachments',new=AsyncMock(side_effect=RuntimeError('SECRET_QA_TOKEN provider payload'))):
            response=await self.client.post('/care-capture/attachment-summary',json=self.body)
        self.assertEqual(response.status_code,500)
        self.assertNotIn('SECRET_QA_TOKEN',response.text)
    async def test_overload_returns_safe_retryable_service_status(self):
        with patch.object(self.routes.AttachmentSummarizationService,'analyze_attachments',new=AsyncMock(side_effect=DocumentProcessingError('SUMMARY_BUSY'))):
            response=await self.client.post('/care-capture/attachment-summary',json=self.body)
        self.assertEqual(response.status_code,503)
    async def test_invalid_request_is_rejected_before_service(self):
        with patch.object(self.routes.AttachmentSummarizationService,'analyze_attachments',new=AsyncMock()) as operation:
            response=await self.client.post('/care-capture/attachment-summary',json={'user_id':'not-a-uuid'})
        self.assertEqual(response.status_code,422);operation.assert_not_called()
    async def test_not_ready_rejected_before_service(self):
        self.app.state.summary_ready=False
        with patch.object(self.routes.AttachmentSummarizationService,'analyze_attachments',new=AsyncMock()) as operation:
            response=await self.client.post('/care-capture/attachment-summary',json=self.body)
        self.assertEqual(response.status_code,503);operation.assert_not_called()

if __name__=='__main__':unittest.main()
