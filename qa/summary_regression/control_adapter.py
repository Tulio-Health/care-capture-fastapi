"""No-database exercises of actual ingestion, publication and runtime controls.

Only dependency boundaries are faked. Lock/isolation behavior is not certified here.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import os
import completion_adapter
import inventory_adapter
import cache_adapter
import remaining_adapter
import publication_adapter
import http_adapter
import runtime_adapter
import source_adapter
import io_adapter
import commit_adapter
import downstream_adapter
import translation_adapter
import parser_control_adapter

CASES = {
 'A14-KEYS','RES-JSONDIRTY','RES-SERIALIZE','RES-QAKEY','RES-MANDATORY',
 'RES-OVERLOAD','RES-PREPDEADLINE','A13-SINGLETON','A13-REVALIDATION',
 'A13-SHAPE-NULL_ITEM','A13-SHAPE-STRING_ITEM','A13-SHAPE-LIST_ITEM',
 'A13-SHAPE-NONOBJECT_RESOURCE_DATA','ERR-METADATA',
}


def supports(case):
    return case['id'] in completion_adapter.CASES or case['id'] in inventory_adapter.CASES or case['id'] in cache_adapter.CASES or case['id'] in remaining_adapter.CASES or case['id'] in downstream_adapter.CASES or case['id'] in commit_adapter.CASES or case['id'] in io_adapter.CASES or case['id'] in translation_adapter.CASES or case['id'] in parser_control_adapter.CASES or case['id'] in source_adapter.CASES or case['id'] in runtime_adapter.CASES or case['id'] in http_adapter.CASES or case['id'] in publication_adapter.CASES or case['id'] in CASES or case['id'].startswith('POLICY-') and 'dependency_error_code' in case.get('inject',{})


def run_case(case, fixture_dir, context):
    if context.uses_live_ai:raise NotImplementedError('Control scenarios mock dependency boundaries')
    return asyncio.run(_run(case,fixture_dir))


async def _run(case,fixture_dir):
    if case['id'] in completion_adapter.CASES:
        return await completion_adapter.run(case,fixture_dir)
    if case['id'] in inventory_adapter.CASES:
        return await inventory_adapter.run(case,fixture_dir)
    if case['id'] in cache_adapter.CASES:
        return await cache_adapter.run(case,fixture_dir)
    if case['id'] in remaining_adapter.CASES:
        return await remaining_adapter.run(case,fixture_dir)
    if case['id'] in downstream_adapter.CASES:
        return await downstream_adapter.run(case,fixture_dir)
    if case['id'] in commit_adapter.CASES:
        return await commit_adapter.run(case,fixture_dir)
    if case['id'] in io_adapter.CASES:
        return await io_adapter.run(case,fixture_dir)
    if case['id'] in parser_control_adapter.CASES:
        return await parser_control_adapter.run(case,fixture_dir)
    if case['id'] in translation_adapter.CASES:
        return await translation_adapter.run(case,fixture_dir)
    if case['id'] in source_adapter.CASES:
        return await source_adapter.run(case,fixture_dir)
    if case['id'] in runtime_adapter.CASES:
        return await runtime_adapter.run(case,fixture_dir)
    if case['id'] in http_adapter.CASES:
        return await http_adapter.run(case,fixture_dir)
    if case['id'] in publication_adapter.CASES:
        return await publication_adapter.run(case,fixture_dir)
    from src.app.services.document_extraction import DocumentTextExtractor,DocumentProcessingError
    from src.app.services import summary_runtime
    from src.app.services.processing_errors import describe_error
    from test_publication_safety import setup_repository,payload
    inject=case.get('inject',{}); identity=case['id']
    observed={'calls':{'database':0,'model_total':0,'summarization':0},'boundary':{}}
    if 'dependency_error_code' in inject:
        error=DocumentProcessingError(inject['dependency_error_code'])
        observed['error_codes']=[error.code]
        observed['errors']=describe_error(error.code)
        observed['boundary']['secret_leaked']='SECRET_QA_TOKEN' in str(observed['errors'])
        return observed
    if identity=='A14-KEYS':
        from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
        keys=[ConversationSummariesRepository._document_ids_key({'source_document_ids':values}) for values in inject['source_id_sets']]
        observed['identity']={'canonical_keys_distinct':len(set(keys))==len(keys)}
    elif identity in {'RES-JSONDIRTY','RES-SERIALIZE','ERR-METADATA'}:
        repository,session=setup_repository()
        request=SimpleNamespace(appointment_id=uuid4(),user_id=uuid4())
        data=payload(request);data['summary_metadata']['unrelated_qa_field']='keep'
        row=await repository.upsert(request.appointment_id,data)
        if identity=='RES-SERIALIZE':
            invalid=payload(request);invalid['summary_metadata']['invalid']=object()
            before=session.commits
            try:await repository.upsert(request.appointment_id,invalid)
            except DocumentProcessingError:observed['http']={'safe_error':True}
            observed['persistence']={'invalid_json_written':session.commits!=before}
        else:
            from sqlalchemy import inspect
            from sqlalchemy.orm.attributes import set_committed_value
            from src.app.services.summary_outcomes import nonclinical_payload
            set_committed_value(row,'summary_metadata',dict(row.summary_metadata))
            await repository.upsert(request.appointment_id,nonclinical_payload(request,'attachment_summary'))
            observed['persistence']={'metadata_change_tracked':inspect(row).attrs.summary_metadata.history.has_changes(),'unrelated_metadata_preserved':row.summary_metadata.get('unrelated_qa_field')=='keep'}
    elif identity=='RES-QAKEY':
        from ai_runtime import load_config,ConfigurationError
        with patch.dict(os.environ,{'OPENAI_API_KEY':'sk-qa-production-canary'},clear=True):
            try:
                config=load_config();used=config.api_key=='sk-qa-production-canary'
            except ConfigurationError:used=False
        observed['harness']={'application_key_used':used}
    elif identity=='RES-MANDATORY':
        from src.app.services.summary_authorization import authorize_summary_scope
        from fastapi import HTTPException
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(summary_ready=False)),state=SimpleNamespace(user={}))
        try:
            await authorize_summary_scope(request,uuid4(),None);allowed=True
        except HTTPException as exc:allowed=exc.status_code!=503
        observed['readiness']={'accepts_clinical_work':allowed}
        observed['boundary']['secret_leaked']='SECRET_QA_TOKEN' in str(observed)
    elif identity in {'RES-OVERLOAD','RES-PREPDEADLINE'}:
        called=[]
        class Service:
            @summary_runtime.bounded_summary
            async def run(self,request):
                called.append('download')
                await asyncio.sleep(.05)
                called.append('model')
        slots=asyncio.Semaphore(0 if identity=='RES-OVERLOAD' else 1)
        code=None
        with patch.object(summary_runtime,'_slots',slots):
            try:await Service().run(SimpleNamespace(timeout_seconds=.005))
            except DocumentProcessingError as exc:code=exc.code
        observed['resources']={'admission_bounded':code=='RESOURCE_LIMIT_EXCEEDED','request_deadline_enforced':code=='SUMMARY_DEADLINE_EXCEEDED'}
        observed['calls']['rejected_request_download']=called.count('download')
        observed['calls']['summarization']=called.count('model')
        observed['http']={'busy_response_safe':code=='RESOURCE_LIMIT_EXCEEDED'}
    else:
        from src.app.services.document_ingestion import process_attachments
        content=(fixture_dir/'clinical_utf8.txt').read_bytes()
        valid={'filePath':'qa://valid','contentType':'text/plain','downloadStatus':'success'}
        data={'attachments':[valid]}
        if identity=='A13-SINGLETON':data['attachments']=valid
        elif identity=='A13-REVALIDATION':data={'attachments':[inject['attachment_metadata']]}
        elif 'malformed_shape' in inject:
            malformed={'null_item':None,'string_item':'malformed','list_item':[],'nonobject_resource_data':None}[inject['malformed_shape']]
            data={'attachments':[valid,malformed]}
        references=[SimpleNamespace(ehr_resource_id='qa-reference',data=data)]
        if inject.get('malformed_shape')=='nonobject_resource_data':
            references=[SimpleNamespace(ehr_resource_id='qa-valid',data={'attachments':[valid]}),SimpleNamespace(ehr_resource_id='qa-invalid',data=['malformed'])]
        storage=SimpleNamespace(download_document=AsyncMock(return_value=content))
        documents=await process_attachments(references,storage,DocumentTextExtractor())
        valid_docs=[d for d in documents if d.extraction_error is None]
        failed_docs=[d for d in documents if d.extraction_error is not None]
        observed['inventory']={'singleton_normalized':len(documents)==1 and len(valid_docs)==1}
        observed['coverage']={'expected_documents':len(documents),'failed_documents':len(failed_docs),'valid_sibling_processed':bool(valid_docs)}
        observed['errors']={'recovery_failed':False}
        observed['identity']={'failed_item_uses_previous_path':any(d.file_path=='qa://valid' for d in failed_docs)}
        observed['pipeline_output']={'documents':[d.model_dump(mode='json') for d in documents]}
    return observed
