"""Execute authorization, chronology and downstream-source filtering without DB I/O."""
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from uuid import uuid4

CASES={'A12-OWNER','A12-CACHE','A12-DELEGATE','A08-ORDER','GATE-TRANSCRIPT','A17-PLACEHOLDER','A17-UPDATES','GROUND-PLACEHOLDER'}

async def run(case,fixture_dir):
    identity=case['id'];observed={'calls':{'database':0,'model_total':0,'document_download':0,'historical_regeneration':0},'persistence':{'write_calls':0}}
    if identity=='A12-OWNER':
        from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService
        request=SimpleNamespace(appointment_id=uuid4(),user_id=uuid4())
        observed_sql=[]
        async def execute(statement):
            where=str(statement.whereclause);params=statement.compile().params;observed_sql.append(where)
            scoped='user_id' in where and str(request.user_id) in [str(value) for value in params.values()]
            return SimpleNamespace(scalar_one_or_none=lambda:None if scoped else SimpleNamespace(provider_id=None,appointment_date=None,purpose=None,ehr_entity_id='other-patient'))
        service=object.__new__(AttachmentSummarizationService);service.db=SimpleNamespace(execute=execute);service.logger=logging.getLogger('qa.scope')
        try:await service._fetch_appointment_details(request);allowed=True
        except ValueError:allowed=False
        observed['authorization']={'allowed':allowed}
        observed['pipeline_output']={'scope_predicates':observed_sql}
    elif identity.startswith('A12-'):
        from src.app.services.summary_authorization import authorize_summary_scope
        from fastapi import HTTPException
        patient=uuid4();mapped=uuid4();appointment=uuid4()
        trusted=identity=='A12-DELEGATE'
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(summary_ready=True)),state=SimpleNamespace(user={'is_authenticated':True,'clerk_id':str(patient) if trusted else 'qa-clerk','is_internal_service':trusted}))
        # Trusted-service calls skip straight to the 1-query appointment-ownership lookup;
        # direct-caller calls resolve their own users.id then fail delegation (3 queries) -
        # a shared return_value would let either path's mock silently answer the other's query.
        effects=[SimpleNamespace(scalar_one_or_none=lambda:appointment)] if trusted else [SimpleNamespace(scalar_one_or_none=lambda:mapped),SimpleNamespace(scalar_one_or_none=lambda:None),SimpleNamespace(scalar_one_or_none=lambda:None)]
        session=SimpleNamespace(execute=AsyncMock(side_effect=effects))
        try:await authorize_summary_scope(request,patient,session,appointment);allowed=True
        except HTTPException:allowed=False
        observed['authorization']={'allowed':allowed,'patient_mapping_correct':allowed and request.state.user['clerk_id']==str(patient)}
        observed['cache']={'clinical_result_exposed':allowed}
        observed['pipeline_output']={'authorized':allowed,'delegation_boundary':'authenticated Node service' if trusted else 'direct caller mapping'}
        if trusted:
            # A trusted service naming an appointment that belongs to a different patient must
            # still be rejected - the binding is unconditional, not internal-service-exempt.
            mismatched_session=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda:None)))
            try:await authorize_summary_scope(request,patient,mismatched_session,appointment);appointment_mismatch_rejected=False
            except HTTPException:appointment_mismatch_rejected=True
            observed['authorization']['appointment_mismatch_rejected']=appointment_mismatch_rejected
    elif identity=='A08-ORDER':
        from src.app.services.summarization.transcript_summarization import TranscriptSummarizationService
        from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
        from src.app.models.transcript_summarization import TranscriptSummarizationResponse
        segments=json.loads((fixture_dir/'transcript.json').read_text())['segments']
        request=SimpleNamespace(appointment_id=uuid4(),transcripts=[SimpleNamespace(text=s['text'],created_at=datetime.fromtimestamp(s['timestamp'],tz=timezone.utc).isoformat()) for s in segments])
        # Chronology test captures the input before the model boundary.
        captured=[]
        async def capture(text):captured.append(text);raise RuntimeError('Stop at model boundary')
        service=object.__new__(TranscriptSummarizationService);service.logger=logging.getLogger('qa.transcript')
        with patch.object(TranscriptSummarizationChain,'summarize',side_effect=capture):
            try:await service._generate_summary(request)
            except RuntimeError:pass
        text=captured[0]
        observed['model_input']={'segment_ids':[s['id'] for s in sorted(segments,key=lambda s:text.index(s['text']))],'text':text}
    elif identity=='GATE-TRANSCRIPT':
        from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
        from src.app.services.document_extraction import DocumentTextExtractor,DocumentProcessingError
        chain=TranscriptSummarizationChain();operation=AsyncMock();chain._chain=SimpleNamespace(ainvoke=operation)
        with patch.object(DocumentTextExtractor,'_extract_from_rtf',side_effect=DocumentProcessingError('PARSE_FAILED')):
            try:await chain.summarize((fixture_dir/case['fixtures'][0]).read_text())
            except DocumentProcessingError:pass
        observed['boundary']={'raw_content_forwarded':operation.await_count>0};observed['calls']['unvalidated_content_model']=operation.await_count
    else:
        from src.app.services.health_insights.health_insight_generator import HealthInsightGenerator
        from src.app.services.summary_outcomes import nonclinical_payload
        from test_publication_safety import setup_repository,payload
        repo,session=setup_repository();request=SimpleNamespace(appointment_id=uuid4(),user_id=uuid4())
        failed=identity!='A17-UPDATES'
        row=await repo.upsert(request.appointment_id,nonclinical_payload(request,'attachment_summary') if failed else payload(request))
        statements=[]
        async def execute(statement):
            statements.append(statement)
            return SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[row]))
        service=object.__new__(HealthInsightGenerator);service.session=SimpleNamespace(execute=execute);service.logger=logging.getLogger('qa.insights')
        grouped=await service._fetch_patient_visit_summaries(datetime(2026,9,15))
        texts=[s.summary_text for group in grouped.values() for s in group.summaries]
        observed['boundary']={'placeholder_used_as_evidence':row.summary_text in texts if failed else False}
        sql=str(statements[0]);where=sql.split('WHERE')[-1].split('ORDER BY')[0]
        observed['insights']={'coverage_context_preserved':grouped[request.user_id].coverage['unavailable']==(1 if failed else 0),'updated_summary_detected':bool(texts) and 'updated_at' in where and 'created_at' not in where}
        observed['pipeline_output']={str(user):group.model_dump(mode='json') for user,group in grouped.items()}
    return observed
