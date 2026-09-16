"""Actual source services, with inventory/storage/AI dependency boundaries in memory."""
import asyncio
from copy import deepcopy
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

CASES={'A03-INVENTORY','ERROR-UNKNOWNCOUNTS','RES-SOURCECHANGE','RES-MEMBERSHIP',
       'A06-TIMEOUT','A06-CLEANUP','A15-COUNTS','A15-STATUS','A15-VALUES'}

async def run(case,fixture_dir):
    identity=case['id'];inject=case['inject']
    observed={'calls':{'database':0,'summarization':0},'coverage':{},'persistence':{},'clinical':{}}
    if identity.startswith('A15-'):
        from src.app.services.summarization.fhir_analysis import FhirAnalysisService
        service=object.__new__(FhirAnalysisService)
        resources=[]
        for kind,key in [('Condition','fhir_conditions'),('MedicationRequest','fhir_medications'),('Observation','fhir_observations')]:
            resources.extend(SimpleNamespace(resource_type=kind,data=data) for data in inject.get(key,[]))
        resources.extend(SimpleNamespace(resource_type='Condition',data={'codeText':f'Synthetic condition {i+1}','verificationStatus':'confirmed','clinicalStatus':'active'}) for i in range(inject.get('synthetic_conditions',0)))
        grouped=service._group_resources_by_type(resources)
        formatted=service._format_fhir_summary(grouped);roundtrip=json.loads(formatted)
        conditions=service._extract_conditions(resources);medications=service._extract_medications(resources)
        observed['coverage'].update(expected_resources=len(resources),all_resources_accounted=sum(len(v) for v in roundtrip.values())==len(resources) and all(r.data in roundtrip[r.resource_type] for r in resources))
        observed['clinical'].update(refuted_diagnosis_published=any(r.data.get('codeText') in conditions for r in resources if r.resource_type=='Condition' and r.data.get('verificationStatus')=='refuted'),stopped_medication_marked_active=any(m['status']=='active' for m in medications if 'Medication Q' in m['name']),fhir_value_forms_preserved_or_disclosed=roundtrip.get('Observation')==inject.get('fhir_observations'))
        observed['pipeline_output']={'model_input':formatted,'conditions':conditions,'medications':medications}
        return observed
    if identity.startswith('A06-'):
        from src.app.services.summarization.comprehensive_summarization import ComprehensiveSummarizationService
        service=object.__new__(ComprehensiveSummarizationService);service.logger=logging.getLogger('qa.comprehensive')
        cancelled=[];completed=[];cleaned=[]
        async def work(source):
            try:
                await asyncio.sleep(inject['task_delays_ms'][source]/1000)
                completed.append(source);return source
            except asyncio.CancelledError:cancelled.append(source);raise
            finally:cleaned.append(source)
        sources=list(inject['task_delays_ms'])
        results=await service._execute_tasks_with_timeout([work(s) for s in sources],sources,case['config']['overall_timeout_ms']/1000)
        observed['sources']={s:{'outcome':'unavailable' if isinstance(r,Exception) else 'success'} for s,r in zip(sources,results)}
        observed['resources']={'completed_tasks_cancelled':len(set(completed)&set(cancelled)),'pending_tasks_awaited':all(s in cleaned for s in cancelled) and bool(cancelled)}
        observed['pipeline_output']={'completed':completed,'cancelled':cancelled,'cleaned':cleaned}
        return observed
    from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService
    from src.app.models.attachment_summarization import AttachmentSummarizationRequest,AttachmentSummarizationResponse,DocumentAttachment
    from src.app.services.document_ingestion import mark_parsed
    from src.app.services.validated_summary import seal_summary
    from src.app.services.document_extraction import DocumentProcessingError
    from test_publication_safety import setup_repository,payload
    repo,session=setup_repository();request=AttachmentSummarizationRequest(appointment_id=uuid4(),user_id=uuid4())
    service=object.__new__(AttachmentSummarizationService);service.db=session;service.summaries_repo=repo;service.logger=logging.getLogger('qa.attachment')
    appointment=SimpleNamespace(appointment_date=None,purpose=None,ehr_entity_id='qa')
    service._fetch_appointment_details=AsyncMock(return_value=(appointment,'N/A'))
    service._run_ai_analysis=AsyncMock(return_value=seal_summary(AttachmentSummarizationResponse(clinical_summary='Ultrasound ordered; not performed.',documents_analyzed=1)))
    service.s3_client=SimpleNamespace(validate_download_versions=AsyncMock())
    if identity in {'A03-INVENTORY','ERROR-UNKNOWNCOUNTS'}:
        service._fetch_document_references=AsyncMock(side_effect=RuntimeError('synthetic inventory unavailable'))
    else:
        prior=await repo.upsert(request.appointment_id,payload(request));original=prior.summary_text
        reference=SimpleNamespace(ehr_resource_id='qa',data={'attachments':[{'filePath':'qa://source'}]})
        later=deepcopy(reference)
        if identity=='RES-MEMBERSHIP':later.data['attachments'].append({'filePath':'qa://new-source'})
        service._fetch_document_references=AsyncMock(side_effect=[[reference],[later]])
        document=mark_parsed(DocumentAttachment(file_path='qa://source',content_type='text/plain',resource_id='qa',extracted_text='Ultrasound ordered; not performed.'))
        service._process_attachments=AsyncMock(return_value=[document])
        if identity=='RES-SOURCECHANGE':service.s3_client.validate_download_versions.side_effect=DocumentProcessingError('SOURCE_VERSION_CHANGED')
    result=await service.analyze_attachments(request)
    metadata=result.metadata
    observed['outcome']=metadata['processing_outcome'];observed['error_codes']=[e['error'] for e in metadata.get('processing_errors',[])]
    observed['calls']['summarization']=service._run_ai_analysis.await_count
    observed['coverage']['expected_documents']=metadata.get('total_documents')
    observed['attempt']={'outcome':'failed' if metadata['processing_outcome']=='unavailable' else metadata.get('last_refresh_outcome',{}).get('processing_outcome')}
    if identity.startswith('RES-'):
        refreshed=metadata.get('last_refresh_outcome',{}).get('processing_outcome')=='unavailable'
        observed['persistence'].update(stale_manifest_published=not refreshed,prior_clinical_content_preserved=original in result.summary_text,pruned_from_stale_manifest=bool(session.deleted))
    observed['pipeline_output']=result.model_dump(mode='json',by_alias=True)
    return observed
