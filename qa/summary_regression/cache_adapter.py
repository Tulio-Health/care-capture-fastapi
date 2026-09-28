"""Actual attachment service cache decisions with freshly parsed synthetic bytes."""
from copy import deepcopy
from hashlib import sha256
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

CASES={'A16-RULEVERSION','A02-CACHE','A02-FIELDS','A02-SERIALIZE','A02-QUERY','A11-FRESH','A11-CHANGED','A11-VERSION','A11-PLACEHOLDER','A11-ADDED','A11-PARTIAL','A11-FORCE'}

async def run(case, fixture_dir):
    from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService
    from src.app.models.attachment_summarization import AttachmentSummarizationRequest, AttachmentSummarizationResponse, DocumentAttachment
    from src.app.models.conversation_summaries import ConversationSummary
    from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
    from src.app.services.document_ingestion import mark_parsed
    from src.app.services.summary_outcomes import source_manifest
    from src.app.services.summary_cache import attachment_fingerprint
    from src.app.services.validated_summary import seal_summary
    from test_publication_safety import setup_repository, payload
    repo,session=setup_repository();identity=case['id']
    request=AttachmentSummarizationRequest(appointment_id=uuid4(),user_id=uuid4(),force_regenerate=case['config'].get('force_regenerate',False))
    service=object.__new__(AttachmentSummarizationService);service.db=session;service.summaries_repo=repo;service.logger=logging.getLogger('qa.cache')
    appointment=SimpleNamespace(appointment_date=None,purpose=None,ehr_entity_id='qa')
    settings=SimpleNamespace(DOCUMENT_VERIFICATION_MODEL='qa-verifier',DOCUMENT_OCR_MODEL='qa-ocr',ENABLE_DOCUMENT_OCR=True,ENABLE_DOCUMENT_TRANSPORT=False,ENABLE_DOCUMENT_CONTAINERS=False)
    content=(fixture_dir/'clinical_utf8.txt').read_bytes()
    document=mark_parsed(DocumentAttachment(file_path='qa://clinical',content_type='text/plain',resource_id='qa',extracted_text=DocumentTextExtractor().extract_text(content,'text/plain'),content_sha256=sha256(content).hexdigest()))
    documents=[document];references=[SimpleNamespace(ehr_resource_id='qa',data={'attachments':[{'filePath':'qa://clinical'}]})]
    if identity=='A16-RULEVERSION':
        from src.app.services.document_type_rules_client import DocumentTypeRulesClient
        rules=DocumentTypeRulesClient();rules._fetch_rules=AsyncMock(return_value=[{'action':'exclude','matchValue':'Insurance'}])
        _,provenance=await rules.resolve_rules()
        service.fhir_repo=SimpleNamespace(eligibility_provenance=provenance)
    context=service._build_appointment_context(appointment,'N/A')
    if service._inventory_context():context['document_eligibility']=service._inventory_context()
    fingerprint=attachment_fingerprint(documents,source_manifest(references),context,settings)
    prior=json.loads((fixture_dir/('rich_prior_state.json' if identity.startswith('A02-') and identity!='A02-CACHE' else 'prior_state.json')).read_text())['summary']
    data=payload(request);data.update(deepcopy(prior));data['id']=UUID(data['id']);data['created_by']=UUID(data['created_by'])
    data['summary_metadata'].update(source='attachment_summary',source_fingerprint=fingerprint,processing_outcome='complete',validation_status='passed',is_clinical_summary=True)
    row=await repo.upsert(request.appointment_id,data)
    before=ConversationSummary.model_validate(row).model_dump();created_by=row.created_by
    other=await repo.upsert(request.appointment_id,payload(request,source='transcript'));other_before=ConversationSummary.model_validate(other).model_dump()
    if identity=='A16-RULEVERSION':
        rules.invalidate_cache();rules._last_known_good=[{'action':'exclude','matchValue':'Billing'}];rules._fetch_rules=AsyncMock(side_effect=OSError('Synthetic rules outage'))
        _,service.fhir_repo.eligibility_provenance=await rules.resolve_rules()
    if identity=='A11-CHANGED':
        changed=content+b'\nFollow-up: Return tomorrow.\n';document.content_sha256=sha256(changed).hexdigest();document.extracted_text=DocumentTextExtractor().extract_text(changed,'text/plain');mark_parsed(document)
    elif identity=='A11-ADDED':documents.append(document.model_copy(update={'resource_id':'new','file_path':'qa://new'}));references.append(SimpleNamespace(ehr_resource_id='new',data={'attachments':[{'filePath':'qa://new'}]}))
    elif identity=='A11-PLACEHOLDER':row.summary_metadata['is_clinical_summary']=False;row.summary_metadata['processing_outcome']='unavailable'
    elif identity=='A11-PARTIAL':row.summary_metadata['processing_outcome']='partial'
    elif identity=='A11-VERSION':row.summary_metadata['source_fingerprint']='previous-processing-version'
    elif identity=='A02-SERIALIZE':row.created_by=None
    elif identity=='A02-QUERY':repo.get_by_appointment_id_and_source=AsyncMock(side_effect=OSError('Synthetic lookup failure'))
    service._fetch_appointment_details=AsyncMock(return_value=(appointment,'N/A'))
    service._fetch_document_references=AsyncMock(return_value=references)
    service._process_attachments=AsyncMock(return_value=documents)
    service._run_ai_analysis=AsyncMock(return_value=seal_summary(AttachmentSummarizationResponse(clinical_summary='Ultrasound ordered; not performed.',documents_analyzed=len(documents))))
    service.s3_client=SimpleNamespace(validate_download_versions=AsyncMock())
    result=None;error=None
    with patch('src.app.core.settings.get_settings',return_value=settings):
        try:result=await service.analyze_attachments(request)
        except DocumentProcessingError as exc:error=exc.code
    hit=result is not None and service._run_ai_analysis.await_count==0
    clinical=('summary_text','key_points','medications','diagnoses','instructions','recommendations','data')
    return {'calls':{'database':0,'summarization':service._run_ai_analysis.await_count},
            'cache':{'hit':hit,'created_by_preserved':bool(result and result.created_by==created_by),'all_clinical_fields_preserved':bool(result and all(result.model_dump()[k]==before[k] for k in clinical)),'lookup_error_reported':error=='PERSISTENCE_FAILED'},
            'inventory':{'rule_provenance_recorded':bool(result and result.metadata.get('document_rule_provenance')==getattr(getattr(service,'fhir_repo',None),'eligibility_provenance',None))},
            'persistence':{'other_source_unchanged':ConversationSummary.model_validate(other).model_dump()==other_before},
            'pipeline_output':{'result':result.model_dump(mode='json',by_alias=True) if result else None,'error_code':error,'source_reads':service._process_attachments.await_count,'version_checks':service.s3_client.validate_download_versions.await_count}}
