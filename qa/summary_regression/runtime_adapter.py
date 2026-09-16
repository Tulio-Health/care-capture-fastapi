"""Failure injection at worker, model, HTTP deadline and logging boundaries."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

CASES={'LIMIT-PARSER','CANCEL-WORKER','RES-WORKERCRASH','CONTRACT-TEXT','CONTRACT-MARKUP',
       'POLICY-RETRYAFTER','ERR-RETRY','ERR-LOG','ERROR-CORRELATION','RES-POOLWAIT',
       'RES-FACTORY','RES-REPORTIO','A16-CLASSIDS','GATE-METADATA-INFERENCE'}

async def run(case, fixture_dir):
    from src.app.services.document_extraction import DocumentProcessingError,DocumentTextExtractor
    from src.app.services import summary_runtime
    observed={'calls':{'database':0,'summarization':0,'model_total':0},'resources':{},'boundary':{}}
    identity=case['id']
    if identity in {'LIMIT-PARSER','CANCEL-WORKER','RES-WORKERCRASH'}:
        # Actual child process and actual application cleanup; only worker workload is injected.
        original=asyncio.create_subprocess_exec;wait_for=asyncio.wait_for;processes=[];spawned=asyncio.Event()
        async def spawn(*args,**kwargs):
            script='import sys; sys.exit(7)' if identity=='RES-WORKERCRASH' else 'import time; time.sleep(60)'
            process=await original(sys.executable,'-c',script,**kwargs);processes.append(process);spawned.set();return process
        async def short_wait(awaitable,timeout):return await wait_for(awaitable,.05)
        with patch('src.app.services.document_extraction.asyncio.create_subprocess_exec',side_effect=spawn),patch('src.app.services.document_extraction.asyncio.wait_for',side_effect=short_wait):
            task=asyncio.create_task(DocumentTextExtractor().extract_text_async(b'Ultrasound ordered.','text/plain'))
            await spawned.wait()
            if identity=='CANCEL-WORKER':task.cancel()
            try:await task
            except asyncio.CancelledError:observed['attempt']={'state':'cancelled'}
            except DocumentProcessingError as exc:observed['error_codes']=[exc.code]
        observed['resources'].update(worker_terminated=bool(processes) and all(p.returncode is not None for p in processes),orphan_workers=sum(p.returncode is None for p in processes))
        observed['resources']['unrelated_requests_healthy']=await DocumentTextExtractor().extract_text_async(b'Clinical note: ultrasound ordered.','text/plain')=='Clinical note: ultrasound ordered.'
        observed['persistence']={'unsafe_draft_saved':False}
    elif identity in {'CONTRACT-TEXT','CONTRACT-MARKUP'}:
        from src.app.models.attachment_summarization import DocumentAttachment
        from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
        content='Ultrasound ordered.' if identity=='CONTRACT-TEXT' else (fixture_dir/case['fixtures'][0]).read_text()
        doc=DocumentAttachment(file_path='qa://untrusted',content_type='text/plain',extracted_text=content)
        chain=AttachmentSummarizationChain();agent=SimpleNamespace(run=AsyncMock())
        with patch.object(type(chain),'extraction_agent',new=property(lambda self:agent)):
            try:await chain.analyze({},[doc])
            except DocumentProcessingError as exc:observed['error_codes']=[exc.code]
        observed['calls']['summarization']=agent.run.await_count
        observed['boundary']['raw_content_forwarded']=agent.run.await_count>0
    elif identity in {'POLICY-RETRYAFTER','ERR-RETRY'}:
        class RateLimitError(Exception):
            status_code=429
            response=SimpleNamespace(headers={'retry-after':'1'})
        operation=AsyncMock(side_effect=[RateLimitError(), 'success']);delays=[]
        async def sleep(delay):delays.append(delay)
        budget=summary_runtime.WorkBudget(deadline=time.monotonic()+5)
        token=summary_runtime._current_budget.set(budget)
        try:
            with patch.object(summary_runtime.asyncio,'sleep',side_effect=sleep):result=await summary_runtime.model_call(operation)
        finally:summary_runtime._current_budget.reset(token)
        observed['calls']['model_total']=operation.await_count
        observed['outcome']=result
        observed['retry']={'provider_delay_honored':bool(delays) and min(delays)>=1,'within_deadline':sum(delays)<5}
    elif identity in {'ERR-LOG','ERROR-CORRELATION'}:
        from starlette.requests import Request
        from starlette.responses import Response
        from src.app.common.middleware import request_logging
        from src.app.services.summary_outcomes import MESSAGES
        external=case['inject'].get('external_correlation_id','SECRET_QA_TOKEN')
        request=Request({'type':'http','method':'POST','path':'/care-capture/attachment-summary','query_string':b'token=SECRET_QA_TOKEN','headers':[(b'authorization',b'SECRET_QA_TOKEN'),(b'x-request-id',external.encode())]},receive=AsyncMock(side_effect=AssertionError('body must not be read')))
        with patch.object(request_logging,'logger') as log:
            response=await request_logging.RequestLoggingMiddleware(None).dispatch(request,AsyncMock(return_value=Response(MESSAGES['unavailable'])))
        logs=str(log.mock_calls);identifier=response.headers['x-request-id']
        observed['logs']={'text':logs};observed['display']={'text':response.body.decode()}
        observed['boundary']['secret_leaked']='SECRET_QA_TOKEN' in logs+response.body.decode()
        observed['errors']={'diagnostic_id_server_owned':str(UUID(identifier))==identifier and identifier!=external,'external_id_sanitized':external not in logs+identifier}
    elif identity=='RES-POOLWAIT':
        from src.app.common.middleware.summary_deadline import SummaryDeadlineMiddleware
        from test_publication_safety import setup_repository,payload
        repo,session=setup_repository();request=SimpleNamespace(appointment_id=__import__('uuid').uuid4(),user_id=__import__('uuid').uuid4())
        row=await repo.upsert(request.appointment_id,payload(request));text=row.summary_text
        async def app(scope,receive,send):await asyncio.Event().wait()
        messages=[]
        async def send(message):messages.append(message)
        await SummaryDeadlineMiddleware(app,timeout_seconds=.01)({'type':'http','path':'/care-capture/attachment-summary'},AsyncMock(),send)
        observed['resources']['wait_deadline_enforced']=messages[0]['status']==503
        observed['persistence']={'prior_clinical_content_preserved':row.summary_text==text}
    elif identity=='RES-FACTORY':
        from src.app.core.settings import Settings
        with patch.dict(os.environ,{'LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false'},clear=True):
            settings=Settings(_env_file=None,OPENAI_API_KEY='sk-qa-unused',DB_HOST='qa.invalid',DB_USER='qa',DB_PASSWORD='unused')
        with patch('src.app.core.settings.get_settings',return_value=settings),patch('src.app.core.get_settings',return_value=settings):
            from src.app.application import get_application
            @asynccontextmanager
            async def lifespan(app):yield
            with patch('src.app.core.scheduler.init_scheduler') as scheduler,patch('src.app.db.config.database.get_engine') as engine,patch('src.app.config.environment.initialize_environment_sync') as environment:
                app=get_application(initialize_environment=False,lifespan_handler=lifespan)
                observed['calls'].update(ssm=environment.call_count,database=engine.return_value.connect.call_count + engine.return_value.begin.call_count,background_job_start=scheduler.call_count)
                observed['http']={'real_routes_registered':any(r.path=='/care-capture/attachment-summary' for r in app.routes)}
    elif identity=='RES-REPORTIO':
        import reporting
        data=dict(cases=[],counts={},state='running',planned_executions=0,fixtures={},requirements=[],run_id='qa',mode='mock',updated_at='now',pack_case_count=0,not_selected_case_count=0,scope='qa',application_adapter='qa',ai=None)
        with patch.object(Path,'write_text',side_effect=OSError('synthetic read-only results folder')) as writer:
            try:reporting.write_report(fixture_dir.parent/'results',data);succeeded=True
            except OSError:succeeded=False
        observed['harness']={'false_success':succeeded or writer.call_count==0}
    elif identity=='GATE-METADATA-INFERENCE':
        from src.app.models.document_type_inference import DocumentTypeInferenceRequest
        from pydantic import ValidationError
        try:DocumentTypeInferenceRequest(id='qa',document_body=(fixture_dir/case['fixtures'][0]).read_text());rejected=False
        except ValidationError:rejected=True
        observed['classification']={'raw_body_rejected':rejected};observed['calls']['document_parser']=0
    elif identity=='A16-CLASSIDS':
        from src.app.chains.document_type_inference.chain import DocumentTypeInferenceChain
        from src.app.models.document_type_inference import DocumentTypeInferenceRequest,DocumentTypeInferenceResponse
        items=[DocumentTypeInferenceRequest(id=i) for i in case['inject']['classification_input_ids']]
        output=[DocumentTypeInferenceResponse(id=i,normalized_type='Clinical note',include_for_summary=True,is_procedure_document=False,confidence=.9) for i in case['inject']['classification_output_ids']]
        chain=DocumentTypeInferenceChain();chain._agent=SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(output=output)))
        try:await chain.infer_batch(items);rejected=False
        except DocumentProcessingError as exc:rejected=exc.code=='MODEL_OUTPUT_INVALID'
        observed['classification']={'unresolved_ids_reported':rejected,'duplicate_ids_rejected':rejected}
    return observed
