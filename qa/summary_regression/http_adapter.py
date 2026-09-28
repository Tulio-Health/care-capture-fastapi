"""Real route execution and serialization; injected services never connect to storage."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

CASES = {'ERR-DB','ERROR-REQUEST','ERROR-MODEL422','ERROR-UNEXPECTED','RES-ALIASES','ERR-NONE'}

async def run(case, fixture_dir):
    from test_http_safety import HttpSafety
    from src.app.services.document_extraction import DocumentProcessingError
    from src.app.services.summary_outcomes import nonclinical_payload
    from src.app.models.conversation_summaries import ConversationSummary
    harness=HttpSafety();await harness.asyncSetUp()
    try:
        operation=AsyncMock()
        identity=case['id'];path='/care-capture/attachment-summary'
        owner=harness.routes.AttachmentSummarizationService;method='analyze_attachments'
        body=harness.body
        if identity=='ERROR-REQUEST': body={'user_id':'not-a-uuid'}
        elif identity=='ERR-DB': operation.side_effect=DocumentProcessingError('PERSISTENCE_FAILED')
        elif identity=='ERROR-MODEL422': operation.side_effect=DocumentProcessingError('MODEL_OUTPUT_INVALID')
        elif identity=='ERROR-UNEXPECTED': operation.side_effect=RuntimeError('SECRET_QA_TOKEN synthetic failure')
        elif identity=='ERR-NONE':
            # Execute the actual empty procedure publication branch, then let the route map its failure.
            from test_publication_safety import setup_repository
            import logging
            owner=harness.routes.ProcedureSummarizationService;method='analyze_procedures';path='/care-capture/procedure-summary'
            service=object.__new__(owner);repo,session=setup_repository()
            service.summaries_repo=repo;service.db=session;service.logger=logging.getLogger('qa.procedure')
            async def fail(*args,**kwargs):
                return await service._persist(harness.request,[],0,[{'error':'PARSE_FAILED'}])
            operation.side_effect=fail
        else:
            data=nonclinical_payload(harness.request,'attachment_summary')
            data.update(id=uuid4(),appointment_id=harness.request.appointment_id,created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))
            operation.return_value=ConversationSummary.model_validate(data)
        with patch.object(owner,method,new=operation):
            response=await harness.client.post(path,json=body)
        wire=response.json()
        return {'http':{'status':response.status_code,'blames_user_input':response.status_code==422,
                        'has_summaryText':'summaryText' in wire,'has_summaryMetadata':'summaryMetadata' in wire,
                        'public_contract_unchanged':set(wire)=={'id','appointmentId','userId','summaryText','keyPoints','medications','diagnoses','instructions','recommendations','data','summaryMetadata','createdAt','updatedAt','createdBy','updatedBy'}},
                'boundary':{'secret_leaked':'SECRET_QA_TOKEN' in response.text},
                'calls':{'model_total':0,'database':0},
                'error_codes':['INTERNAL_PROCESSING_ERROR'] if response.status_code==500 and identity=='ERROR-UNEXPECTED' else [],
                'persistence':{'claimed_saved':response.status_code==200,'created_procedure_rows':len(session.rows) if identity=='ERR-NONE' else 0},
                'pipeline_output':{'http_body':wire,'status':response.status_code}}
    finally: await harness.asyncTearDown()
