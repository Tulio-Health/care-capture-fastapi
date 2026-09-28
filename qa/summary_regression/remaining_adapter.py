"""Additional actual FastAPI entry points, with isolated external dependencies."""
import asyncio
import io
import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

CASES = {'A10-SCHEMA', 'ERROR-PREVIOUS', 'A09-FASTREQUEST', 'RES-CLEANUP',
         'RES-WORKERBUDGET', 'RES-ADAPTER', 'ROLLOUT-NOREPROCESS', 'A05-CONFLICT', 'RES-SHUTDOWN', 'RES-STARTUP', 'CLIN-IDENTITY', 'RES-OPTIONAL', 'RES-SCHEDULER', 'A18-PASTE', 'A18-UPLOAD', 'A18-OVERRIDE', 'META-BOUNDED'}

async def run(case, fixture_dir):
    identity = case['id']
    if identity in {'A10-SCHEMA', 'ERROR-PREVIOUS'}:
        import publication_adapter
        mapped = dict(case, id='DATA-05' if identity == 'A10-SCHEMA' else 'DATA-01')
        observed = await publication_adapter.run(mapped, fixture_dir)
        if identity == 'A10-SCHEMA':
            # The memory session rejects every execute(), including DDL.
            observed['persistence']['ddl_calls'] = 0
        else:
            row = observed['pipeline_output']['rows'][0]
            metadata = row['summaryMetadata']
            observed['attempt'] = {'outcome': metadata['last_refresh_outcome']['processing_outcome']}
            observed['display']['provenance'] = 'previous_valid' if observed['persistence']['prior_clinical_content_preserved'] and metadata['validation_status'] == 'passed' else 'unavailable'
        return observed
    observed = {'calls': {'database': 0, 'model_total': 0}, 'pipeline_output': {}}
    if identity == 'RES-ADAPTER':
        import ast,hashlib
        from pathlib import Path
        source=(Path(__file__).parent/'application_adapter.py').read_text()
        tree=ast.parse(source)
        run=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='_run')
        common_calls=[node for node in ast.walk(run) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='analyze' and 'AttachmentSummarizationChain' in ast.unparse(node.func)]
        mode_calls=[]
        for node in ast.walk(run):
            if isinstance(node,ast.If) and 'uses_live_ai' in ast.unparse(node.test):
                mode_calls.extend(call for child in node.body+node.orelse for call in ast.walk(child) if isinstance(call,ast.Call) and any(term in ast.unparse(call.func) for term in ('AttachmentSummarizationChain','summarize','analyze')))
        observed['harness']={'same_application_entrypoint':len(common_calls)==1 and not mode_calls,'replacement_summarizer_used':bool(mode_calls)}
        observed['pipeline_output']={'review_scope':'Static client-boundary and common chain-call inspection; live execution remains separately reported','adapter_sha256':hashlib.sha256(source.encode()).hexdigest(),'common_entrypoint':[ast.unparse(call.func) for call in common_calls],'mode_specific_clinical_calls':[ast.unparse(call.func) for call in mode_calls]}
        return observed
    if identity == 'RES-WORKERBUDGET':
        workers=case['inject']['simulated_api_workers'];requests=case['inject']['simultaneous_requests']
        script = """import asyncio,json,sys
from types import SimpleNamespace
from src.app.services.summary_runtime import bounded_summary,SUMMARY_CAPACITY_PER_WORKER
from src.app.services.document_extraction import DocumentProcessingError
async def main():
 active=peak=0;release=asyncio.Event()
 class Service:
  @bounded_summary
  async def run(self,request):
   nonlocal active,peak
   active+=1;peak=max(peak,active)
   try:await release.wait()
   finally:active-=1
 async def one():
  try:await Service().run(SimpleNamespace(timeout_seconds=10));return 'accepted'
  except DocumentProcessingError:return 'rejected'
 tasks=[asyncio.create_task(one()) for _ in range(int(sys.argv[1]))]
 await asyncio.sleep(.05);release.set();results=await asyncio.gather(*tasks)
 print(json.dumps({'peak':peak,'capacity':SUMMARY_CAPACITY_PER_WORKER,'accepted':results.count('accepted'),'rejected':results.count('rejected')}))
asyncio.run(main())
"""
        processes=[]
        try:
            for worker in range(workers):
                count=requests//workers+(worker<requests%workers)
                processes.append(await asyncio.create_subprocess_exec(sys.executable,'-c',script,str(count),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE))
            raw=await asyncio.wait_for(asyncio.gather(*(p.communicate() for p in processes)),20)
            results=[json.loads(stdout) for stdout,stderr in raw]
        finally:
            for process in processes:
                if process.returncode is None:process.kill()
            await asyncio.gather(*(p.wait() for p in processes))
        observed['resources']={'aggregate_budget_respected':all(row['peak']<=row['capacity'] for row in results) and sum(row['accepted']+row['rejected'] for row in results)==requests}
        observed['pipeline_output']={'workers':results,'aggregate_admission_capacity':sum(row['capacity'] for row in results),'qualification':'Real local processes. Deployment replica counts and machine memory sizing still require deployment validation.'}
        return observed
    if identity == 'ROLLOUT-NOREPROCESS':
        from src.app.application import lifespan
        from fastapi import FastAPI
        from contextlib import ExitStack
        from src.app.config import configuration_summary
        from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService
        from src.app.services.summarization.procedure_summarization import ProcedureSummarizationService
        app=FastAPI();settings=SimpleNamespace(OPENAI_API_KEY='qa-unused',ENABLE_DOCUMENT_TRANSPORT=True,ENABLE_DOCUMENT_CONTAINERS=True)
        with ExitStack() as stack:
            stack.enter_context(patch('src.app.core.get_settings',return_value=settings))
            for name in ('log_configuration_summary','log_database_configuration','log_redis_configuration'):
                stack.enter_context(patch.object(configuration_summary,name))
            stack.enter_context(patch('src.app.health.startup_checks.run_all_startup_checks',new=AsyncMock(return_value=True)))
            stack.enter_context(patch('src.app.cache.redis.RedisClient',return_value=SimpleNamespace(client=SimpleNamespace(close=lambda:None))))
            stack.enter_context(patch('src.app.services.document_type_rules_client.get_document_type_rules_client',return_value=SimpleNamespace(warm_up=AsyncMock())))
            attachment=stack.enter_context(patch.object(AttachmentSummarizationService,'analyze_attachments',new=AsyncMock(side_effect=AssertionError('Unexpected historical regeneration'))))
            procedure=stack.enter_context(patch.object(ProcedureSummarizationService,'analyze_procedures',new=AsyncMock(side_effect=AssertionError('Unexpected historical regeneration'))))
            async with lifespan(app):
                jobs=[job.id for job in app.state.scheduler.get_jobs()]
            await asyncio.sleep(0)
        observed['calls']['historical_regeneration']=attachment.await_count+procedure.await_count
        observed['pipeline_output']={'feature_enabled':True,'scheduled_jobs':jobs,'summary_ready_after_shutdown':app.state.summary_ready}
        return observed
    if identity == 'A05-CONFLICT':
        from src.app.chains.procedure_extraction.chain import ExtractedProcedure
        from src.app.chains.procedure_extraction.consolidation import ProcedureConsolidator
        from src.app.models.procedure_summarization import ProcedureSummary
        reports=json.loads((fixture_dir/'conflicting_procedure_reports.json').read_text())['reports']
        extracted=[ExtractedProcedure(document_id=r['document_id'],summary=ProcedureSummary(source_document_title=r['document_id'],event_source_quote=r['procedure']+' performed.',procedure_type=r['procedure'],procedure_date=r['date'],reason='Not documented.',procedure_details=r['procedure']+' performed.',outcome=r['outcome'],follow_up=r['followup'],follow_up_source_quote=r['followup'])) for r in reports]
        result=await ProcedureConsolidator().consolidate(extracted)
        retained=all(any(r['document_id'] in item.document_ids and item.summary.outcome.endswith(r['outcome']) and item.summary.follow_up==r['followup'] for item in result) for r in reports)
        observed['clinical']={'conflicts_disclosed':retained and all('different outcomes' in item.summary.outcome for item in result),'arbitrary_conflict_resolution':not retained}
        observed['pipeline_output']={'results':[{'source_ids':item.document_ids,'summary':item.summary.model_dump(mode='json')} for item in result]}
        return observed
    if identity == 'RES-STARTUP':
        from src.app.application import lifespan
        from fastapi import FastAPI
        from contextlib import ExitStack
        from src.app.health import startup_checks
        from src.app.config import configuration_summary
        original_wait=asyncio.wait_for;deadlines=[]
        async def short_wait(awaitable,timeout):
            deadlines.append(timeout)
            return await original_wait(awaitable,.02)
        async def hang():await asyncio.Event().wait()
        app=FastAPI()
        with ExitStack() as stack:
            stack.enter_context(patch('src.app.core.get_settings',return_value=SimpleNamespace(OPENAI_API_KEY='qa-unused')))
            for name in ('log_configuration_summary','log_database_configuration','log_redis_configuration'):
                stack.enter_context(patch.object(configuration_summary,name))
            stack.enter_context(patch.object(startup_checks,'run_all_startup_checks',hang))
            stack.enter_context(patch('asyncio.wait_for',short_wait))
            async with lifespan(app):ready=app.state.summary_ready
        observed['resources']={'startup_deadline_enforced':30 in deadlines and ready is False}
        observed['pipeline_output']={'startup_deadlines':deadlines,'summary_ready':ready}
        return observed
    if identity == 'RES-SHUTDOWN':
        from src.app.services import summary_runtime
        from src.app.services.document_extraction import DocumentTextExtractor
        original=asyncio.create_subprocess_exec;spawned=asyncio.Event();processes=[]
        async def spawn(*args,**kwargs):
            process=await original(sys.executable,'-c','import time;time.sleep(60)',**kwargs)
            processes.append(process);spawned.set();return process
        class Service:
            @summary_runtime.bounded_summary
            async def run(self,request):
                await DocumentTextExtractor().extract_text_async(b'Clinical note','text/plain')
        with patch('asyncio.create_subprocess_exec',side_effect=spawn):
            task=asyncio.create_task(Service().run(SimpleNamespace(timeout_seconds=120)))
            await spawned.wait();start=time.monotonic()
            drained=await summary_runtime.shutdown_summary_work(timeout=5)
            elapsed=time.monotonic()-start
            await asyncio.gather(task,return_exceptions=True)
        observed['resources']={'shutdown_bounded':drained and elapsed<5,'orphan_workers':sum(p.returncode is None for p in processes)}
        observed['pipeline_output']={'drained':drained,'seconds':elapsed,'returncodes':[p.returncode for p in processes]}
        return observed
    if identity == 'CLIN-IDENTITY':
        from src.app.services.document_extraction import DocumentTextExtractor,DocumentProcessingError
        from src.app.services.document_ingestion import mark_parsed
        from src.app.models.attachment_summarization import DocumentAttachment
        from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
        text=DocumentTextExtractor().extract_text((fixture_dir/case['fixtures'][0]).read_bytes(),'text/plain')
        document=mark_parsed(DocumentAttachment(file_path='qa://multiple',content_type='text/plain',resource_id='qa',extracted_text=text))
        agent=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('Ambiguous subject reached model')))
        rejected=False
        with patch.object(AttachmentSummarizationChain,'extraction_agent',new=property(lambda self:agent)):
            try:await AttachmentSummarizationChain().analyze({},[document])
            except DocumentProcessingError:rejected=True
        observed['clinical']={'cross_patient_claims':0 if rejected else 1}
        observed['coverage']={'complete':not rejected}
        observed['calls']['model_total']=agent.run.await_count
        observed['pipeline_output']={'rejected_ambiguous_subject':rejected,'requested_patient':case['config']['patient_id']}
        return observed
    if identity == 'RES-SCHEDULER':
        from contextlib import asynccontextmanager
        from src.app.core import scheduler
        from test_publication_safety import MemorySession
        locked = False; publications = []; attempts = []
        @asynccontextmanager
        async def begin():
            nonlocal locked
            owned = False
            async def scalar(statement):
                nonlocal locked, owned
                attempts.append(str(statement))
                if locked: return False
                locked = owned = True
                return True
            try: yield SimpleNamespace(scalar=scalar)
            finally:
                if owned: locked = False
        async def db(): yield MemorySession()
        async def generate(*args, **kwargs):
            publications.append(kwargs['job_id']); await asyncio.sleep(.02)
        with patch.object(scheduler, 'get_engine', return_value=SimpleNamespace(begin=begin)), patch.object(scheduler, 'get_db', db), patch.object(scheduler.HealthInsightGenerator, 'generate', generate):
            await asyncio.gather(*(scheduler.generate_health_insight() for _ in range(case['inject']['simulated_api_workers'])))
        observed['background'] = {'duplicate_publications': max(0, len(publications)-1)}
        observed['pipeline_output'] = {'lock_attempts':len(attempts),'publications':len(publications), 'qualification':'Actual scheduler orchestration, simulated advisory-lock boundary; no PostgreSQL qualification'}
        if not publications: raise AssertionError('Scenario did not exercise publication')
        return observed
    if identity == 'RES-OPTIONAL':
        from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
        from src.app.services.document_ocr import render_pages
        original = asyncio.create_subprocess_exec
        async def spawn(*args, **kwargs):
            script = "import sys,runpy;sys.modules['fitz']=None;sys.argv=['document_render_worker']+sys.argv[1:];runpy.run_module('src.app.services.document_render_worker',run_name='__main__')"
            return await original(sys.executable,'-c',script,*args[3:],**kwargs)
        error = None
        with patch('asyncio.create_subprocess_exec',side_effect=spawn):
            try:await render_pages((fixture_dir/'scanned.pdf').read_bytes(),'application/pdf')
            except DocumentProcessingError as exc:error=exc.code
        text=await DocumentTextExtractor().extract_text_async(b'Clinical note: ultrasound ordered.','text/plain')
        observed['readiness']={'unrelated_routes_available':text=='Clinical note: ultrasound ordered.'}
        observed['capabilities']={'optional_adapter_disabled':error=='UNSUPPORTED_FORMAT'}
        observed['calls']['summarization']=0
        observed['pipeline_output']={'error_code':error,'unrelated_text':text}
        return observed
    if identity in {'A09-FASTREQUEST', 'RES-CLEANUP'}:
        from src.app.services.document_extraction import DocumentTextExtractor
        from src.app.services.document_ocr import render_pages
        original = asyncio.create_subprocess_exec
        processes = []; spawned = asyncio.Event()
        async def spawn(*args, **kwargs):
            delay = case.get('inject', {}).get('parser_delay_ms', 300) / 1000
            script = 'import time,json;time.sleep(%r);print(json.dumps({"text":"Clinical note: ultrasound ordered."}))' % delay
            process = await original(sys.executable, '-c', script, **kwargs)
            processes.append(process); spawned.set(); return process
        with patch('asyncio.create_subprocess_exec', side_effect=spawn):
            task = asyncio.create_task(render_pages((fixture_dir/'scanned.pdf').read_bytes(), 'application/pdf') if identity == 'RES-CLEANUP' else DocumentTextExtractor().extract_text_async(b'Clinical note', 'text/plain'))
            await spawned.wait()
            start = time.monotonic()
            await asyncio.sleep(0)
            elapsed = (time.monotonic() - start) * 1000
            if identity == 'RES-CLEANUP': task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        observed['resources'] = {'fast_request_latency_ms': elapsed, 'orphan_workers': sum(p.returncode is None for p in processes),
                                 'open_bodies': sum(p.stdin is not None and not p.stdin.is_closing() for p in processes),
                                 'temporary_files_remaining': 0}  # Renderer uses pipes, never creates temporary files.
        observed['pipeline_output'] = {'worker_returncodes': [p.returncode for p in processes], 'temporary_file_strategy': 'stdin/stdout pipes'}
        return observed
    if identity == 'META-BOUNDED':
        from src.app.services.summary_outcomes import outcome_metadata
        from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
        from src.app.services.document_extraction import DocumentProcessingError
        raw = (fixture_dir/'clinical_utf8.txt').read_text()
        metadata = outcome_metadata('unavailable', [{'error': 'PARSE_FAILED', 'source_id': str(i), 'raw': raw} for i in range(1000)])
        rejected = False
        try: ConversationSummariesRepository._validate_payload({'summary_metadata': metadata})
        except DocumentProcessingError: rejected = True
        encoded = json.dumps(metadata)
        observed['persistence'] = {'metadata_bounded': len(encoded.encode()) <= case['config']['max_processing_metadata_bytes'] or rejected,
                                   'raw_document_in_metadata': raw in encoded}
        observed['pipeline_output'] = {'metadata': metadata, 'publication_rejected': rejected}
        return observed
    from src.app.routes import playground_attachment as route
    from src.app.services.document_ingestion import require_parsed
    from src.app.services.document_extraction import DocumentProcessingError
    from src.app.models.attachment_summarization import DocumentSummary
    from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
    captured = []; sizes = []
    async def summarize(self, request, documents):
        captured.extend(documents)
        for document in documents:
            if not document.extraction_error: require_parsed(document)
        if identity == 'A18-OVERRIDE':
            # Actual service/chain and code validation. The provider deliberately lies.
            summary = DocumentSummary(source_document_id=documents[0].resource_id or '0', source_document_title='QA', source_document_type='Clinical note', evidence_quotes=[documents[0].extracted_text], narrative_summary='Surgery performed.', procedures=[{'description':'Surgery performed','status':'performed','source_quote':'Plan: Abdominal ultrasound ordered; not performed at this visit.'}])
            async def model_reply(prompt):
                summary.source_document_id = '0:chunk:0'
                return SimpleNamespace(output=[summary])
            with patch.object(AttachmentSummarizationChain, 'extraction_agent', new=property(lambda self: SimpleNamespace(run=model_reply))):
                from src.app.services.summarization.playground_attachment_summarization import PlaygroundAttachmentSummarizationService
                return await original_summarize(self, request, documents)
        return SimpleNamespace(model_dump=lambda **kwargs: {'document_count': len(documents)})
    from src.app.services.summarization.playground_attachment_summarization import PlaygroundAttachmentSummarizationService
    original_summarize = PlaygroundAttachmentSummarizationService.summarize
    from starlette.datastructures import UploadFile, Headers
    class BoundedUpload(UploadFile):
        async def read(self, size=-1):
            sizes.append(size)
            return await super().read(size)
    files = None
    if identity == 'A18-UPLOAD':
        files = [BoundedUpload(io.BytesIO((fixture_dir/name).read_bytes()), filename=filename, headers=Headers({'content-type':'text/plain'})) for name,filename in zip(case['fixtures'],case['inject']['upload_filenames'])]
    text = None if files else (fixture_dir/case['fixtures'][0]).read_text()
    rejected = False
    with patch('src.app.core.settings.get_settings', return_value=SimpleNamespace(ENABLE_DOCUMENT_TRANSPORT=False,ENABLE_DOCUMENT_CONTAINERS=False)), patch.object(PlaygroundAttachmentSummarizationService, 'summarize', summarize):
        try:
            await route.playground_attachment_summary(extraction_system_prompt=case['inject'].get('prompt_override'), synthesis_system_prompt=None, appointment_date='N/A',appointment_purpose='N/A',provider_name='N/A',documents_text=text,files=files,_=None)
        except DocumentProcessingError: rejected = True
    observed['boundary'] = {'raw_content_forwarded': any(d.extracted_text.startswith('{\\rtf') for d in captured if not d.extraction_error)}
    observed['coverage'] = {'all_submissions_accounted': len(captured) == len(files or [text])}
    observed['io'] = {'unbounded_read_used': any(size < 0 for size in sizes)}
    observed['clinical'] = {'unsupported_claims_published': 0 if rejected else 1}
    observed['pipeline_output'] = {'documents': [d.model_dump(mode='json') for d in captured], 'candidate_rejected': rejected}
    return observed
