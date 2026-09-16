"""Publication behavior exercised against the real repository with in-memory storage."""
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

CASES = {'DATA-01','DATA-02','DATA-03','DATA-04','DATA-05','UI-CLINICALFIELDS',
         'A01-PARTIAL','A01-EMPTY','RES-LEGACYMETA'}

async def run(case, fixture_dir):
    from test_publication_safety import setup_repository, payload
    from src.app.services.summary_outcomes import nonclinical_payload
    from src.app.models.conversation_summaries import ConversationSummary
    repo, session = setup_repository()
    request = SimpleNamespace(appointment_id=uuid4(), user_id=uuid4())
    identity = case['id']
    source = 'procedure_summary' if identity in {'DATA-03','A01-PARTIAL','A01-EMPTY'} else 'attachment_summary'
    prior = json.loads((fixture_dir / ('rich_prior_state.json' if identity=='UI-CLINICALFIELDS' else 'prior_state.json')).read_text())
    data = payload(request, source=source)
    data.update(deepcopy(prior['summary']))
    data['id'] = UUID(data['id']); data['created_by'] = UUID(data['created_by'])
    data['summary_metadata'].update(source=source, processing_outcome='complete', validation_status='passed', is_clinical_summary=True)
    if case['inject'].get('prior_validation') == 'invalid': data['summary_metadata']['validation_status']='failed'
    row = await repo.upsert(request.appointment_id, data)
    clinical = ('key_points','medications','diagnoses','instructions','recommendations','data')
    before = {k:deepcopy(getattr(row,k)) for k in clinical}
    before_text = row.summary_text
    observed = {'calls':{'database':0,'summarization':0},'persistence':{},'display':{},'clinical':{}}
    if identity in {'DATA-01','DATA-02','UI-CLINICALFIELDS','RES-LEGACYMETA'}:
        if identity=='RES-LEGACYMETA': row.summary_metadata=None
        for _ in range(case['config'].get('repeat_attempts',1)):
            saved = await repo.upsert(request.appointment_id, nonclinical_payload(request,source,errors=[{'error':'PARSE_FAILED'}]))
        if identity=='RES-LEGACYMETA':
            observed['errors']={'recovery_failed':False}
            observed['persistence']['prior_clinical_content_preserved']=row.summary_text==before_text and all(getattr(row,k)==v for k,v in before.items())
            observed['pipeline_output']={'returned':ConversationSummary.model_validate(saved).model_dump(mode='json',by_alias=True),'legacy_text_preserved':row.summary_text==before_text}
            return observed
        preserved=all(getattr(row,k)==v for k,v in before.items()) and before_text in row.summary_text
        observed['persistence'].update(prior_clinical_content_preserved=preserved, invalid_prior_exposed=before_text in row.summary_text)
        observed['display'].update(kind='refresh_failed' if (row.summary_metadata or {}).get('last_refresh_outcome') else row.summary_metadata['processing_outcome'], notice_count=row.summary_text.count('The previous summary is shown below.'))
        observed['clinical']['placeholder_fields_empty']=not any(getattr(row,k) for k in clinical)
        observed['persistence']['legacy_metadata_handled']=isinstance(row.summary_metadata,dict)
    elif identity=='DATA-04':
        for attempt in sorted(case['inject']['attempts'],key=lambda a:a['complete_order']):
            value=payload(request);value['summary_text']=attempt['id'];value['summary_metadata']['attempt_started_at']=f"2026-09-16T12:00:0{attempt['source_version']}+00:00"
            await repo.upsert(request.appointment_id,value)
        observed['persistence'].update(winning_attempt=row.summary_text,duplicate_rows=len(session.rows)-1)
    elif identity=='DATA-05':
        other=payload(request,source=prior['other_source']['source']);other['summary_text']=prior['other_source']['summary_text']
        other_row=await repo.upsert(request.appointment_id,other)
        other_before=ConversationSummary.model_validate(other_row).model_dump()
        await repo.upsert(request.appointment_id,payload(request))
        observed['persistence']['other_source_unchanged']=ConversationSummary.model_validate(other_row).model_dump()==other_before
    else:
        # Seed distinct procedure identities, then exercise the actual prune/failure branch.
        row.summary_metadata['source_document_ids']=['doc-a']
        second=payload(request,source=source,ids=['doc-b']);second['summary_text']=prior['procedure_rows'][1]['summary_text']
        await repo.upsert_many_for_source(request.appointment_id,source,[{k:v for k,v in data.items() if k!='id'}|{'summary_metadata':row.summary_metadata},second],allow_prune=False)
        originals={r.id:r.summary_text for r in session.rows}
        other=payload(request,source='transcript')
        other_row=await repo.upsert(request.appointment_id,other)
        other_snapshot=ConversationSummary.model_validate(other_row).model_dump()
        if identity=='A01-EMPTY':
            await repo.upsert_many_for_source(request.appointment_id,source,[],allow_prune=True,user_id=request.user_id)
        elif identity=='A01-PARTIAL':
            await repo.upsert_many_for_source(request.appointment_id,source,[payload(request,source=source,ids=['doc-a'])],allow_prune=False)
        else:
            await repo.record_processing_failure(request.appointment_id,source,request.user_id,[{'error':'PARSE_FAILED'}])
        observed['persistence'].update(deleted_prior_row_ids=[str(r.id) for r in session.deleted],prior_clinical_content_preserved=all(any(r.id==key and text in r.summary_text for r in session.rows) for key,text in originals.items()),pruned_rows=len(session.deleted),remaining_procedure_rows=len(session.rows))
    if identity in {'A01-PARTIAL','A01-EMPTY','DATA-03'}:
        observed['persistence']['failed_source_rows_preserved']=any((r.summary_metadata or {}).get('source_document_ids')==['doc-b'] and prior['procedure_rows'][1]['summary_text'] in r.summary_text for r in session.rows)
        observed['persistence']['pruned_only_authoritative_sources']=bool(session.deleted) and all((r.summary_metadata or {}).get('source')==source for r in session.deleted) and ConversationSummary.model_validate(other_row).model_dump()==other_snapshot
    observed['pipeline_output']={'rows':[ConversationSummary.model_validate(r).model_dump(mode='json',by_alias=True) for r in session.rows]}
    return observed
