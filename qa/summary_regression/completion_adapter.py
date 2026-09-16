"""Remaining orchestration cases against production services, using memory boundaries."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

CASES = {'A03-FHIRFALLBACK', 'A08-LONGTRANSCRIPT', 'LIMIT-MEMORY'}


async def run(case, fixture_dir):
    from src.app.services.document_extraction import DocumentProcessingError
    if case['id'] == 'LIMIT-MEMORY':
        import asyncio
        import shutil
        import sys
        from pathlib import Path
        limit = case['config']['worker_memory_limit_bytes']
        script = """import sys,json,resource
from src.app.services import document_parser_worker as worker
original=worker.DocumentTextExtractor.extract_text
def allocate(self,*args,**kwargs):
    bytearray(8*1024*1024)
    return 'allocation unexpectedly succeeded'
worker.DocumentTextExtractor.extract_text=allocate
sys.argv=['worker','application/pdf','memory.pdf',json.dumps({'worker_memory_limit_bytes':LIMIT})]
worker.main()
""".replace('LIMIT', str(limit))
        if sys.platform == 'linux':
            command = [sys.executable, '-c', script]
        elif shutil.which('docker'):
            root=Path(__file__).resolve().parents[2]
            command=['docker','run','--rm','--pull=never','--network','none','--memory','128m','--cpus','1','-i','-v',str(root/'src')+':/work/src:ro','-w','/work','python:3.12-slim','python','-c',script]
        else:
            raise NotImplementedError('Linux or a local python:3.12-slim Docker image is needed for real RLIMIT_AS qualification.')
        process=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            output,error=await asyncio.wait_for(process.communicate((fixture_dir/'native.pdf').read_bytes()),45)
        finally:
            if process.returncode is None:process.kill();await process.wait()
        if process.returncode:
            raise NotImplementedError('Linux memory probe could not execute; check local Docker image and daemon availability.')
        result=json.loads(output)
        return {'resources':{'limit_enforced':result.get('error')=='RESOURCE_LIMIT_EXCEEDED'},'calls':{'database':0,'summarization':0},'pipeline_output':{'worker_result':result,'requested_memory_bytes':limit,'allocation_bytes':8*1024*1024,'qualification':'Real Linux RLIMIT_AS allocation failure through production parser worker; no database or model.'}}
    if case['id'] == 'A08-LONGTRANSCRIPT':
        from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
        source = json.loads((fixture_dir/'transcript.json').read_text())
        text = '\n'.join(item['text'] for item in source['segments']) * case['config']['repeat_segments']
        chain = TranscriptSummarizationChain()
        boundary = AsyncMock()
        chain._chain = SimpleNamespace(ainvoke=boundary)
        code = None
        try:
            await chain.summarize(text)
        except DocumentProcessingError as exc:
            code = exc.code
        return {'calls': {'database':0, 'model_total':boundary.await_count}, 'error_codes':[code],
                'resources': {'all_model_calls_within_budget':boundary.await_count==0 and code=='RESOURCE_LIMIT_EXCEEDED'},
                'coverage': {'all_chunks_accounted':boundary.await_count==0 and code=='RESOURCE_LIMIT_EXCEEDED'},
                'pipeline_output': {'summary':None, 'input_characters':len(text), 'disposition':'Entire over-limit input refused before model invocation; no truncated summary.'}}
    from src.app.services.summarization.comprehensive_summarization import ComprehensiveSummarizationService
    from src.app.services.summarization.fhir_analysis import FhirAnalysisService
    from src.app.models.fhir_analysis import FhirAnalysisRequest,FhirAnalysisResponse
    from src.app.models.conversation_summaries import ConversationSummary
    from src.app.services.summary_outcomes import nonclinical_payload
    from test_publication_safety import setup_repository
    repository,session=setup_repository()
    request=SimpleNamespace(appointment_id=uuid4(),user_id=uuid4(),resource_types=None,analysis_focus=None)
    # A real corrupt attachment fails before AI; the stored structured resources are separate evidence.
    from src.app.services.document_extraction import DocumentTextExtractor
    try:DocumentTextExtractor().extract_text((fixture_dir/'corrupt.pdf').read_bytes(),'application/pdf')
    except DocumentProcessingError as exc:failure=exc.code
    prior=await repository.upsert(request.appointment_id,nonclinical_payload(request,'attachment_summary',errors=[{'error':failure}]))
    attachment=ConversationSummary.model_validate(prior)
    service=object.__new__(FhirAnalysisService);service.db=session;service.summaries_repo=repository;service.logger=logging.getLogger('qa.fhir-fallback')
    appointment=SimpleNamespace(appointment_date=None,purpose=None,ehr_entity_id='synthetic-encounter')
    service._fetch_appointment_details=AsyncMock(return_value=(appointment,'N/A'))
    structured=json.loads((fixture_dir/'structured_fhir.json').read_text())
    service._fetch_fhir_resources=AsyncMock(return_value=[SimpleNamespace(resource_type=item['resourceType'],data=item) for item in structured])
    service._run_ai_analysis=AsyncMock(return_value=FhirAnalysisResponse(clinical_summary=structured[0]['codeText'],key_insights=[]))
    orchestrator=object.__new__(ComprehensiveSummarizationService)
    orchestrator._run_attachment_summarization=AsyncMock(return_value=attachment)
    async def fallback(req, *, attachment_failures):
        return await service.analyze_fhir_resources(FhirAnalysisRequest(appointment_id=req.appointment_id,user_id=req.user_id),attachment_failures=attachment_failures)
    orchestrator._run_fhir_analysis=fallback
    result=await orchestrator._run_attachment_with_fhir_fallback(request)
    return {'calls':{'database':0,'summarization':service._run_ai_analysis.await_count},'outcome':result.metadata['processing_outcome'],
            'display':{'text':result.summary_text},'coverage':{'complete':result.metadata['processing_outcome']=='complete'},
            'pipeline_output':result.model_dump(mode='json',by_alias=True),
            'persistence':{'in_memory_rows':[r.summary_text for r in session.rows], 'warning_persisted':any(r.summary_text==result.summary_text for r in session.rows)}}
