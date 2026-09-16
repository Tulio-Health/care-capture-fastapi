"""Commit-acknowledgement and response failure injection with transactional memory state."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

CASES={'A10-PROCEDURES','ERROR-PERSISTRETRY','CANCEL-COMMIT','A19-ACK','A19-REFRESH','A19-RESPONSE','A10-ORM','A10-FIRSTWRITES'}

async def run(case,fixture_dir):
    from test_publication_safety import setup_repository,payload
    from src.app.models.conversation_summaries import ConversationSummary
    from src.app.services.document_extraction import DocumentProcessingError
    repo,session=setup_repository();request=SimpleNamespace(appointment_id=uuid4(),user_id=uuid4())
    identity=case['id'];observed={'calls':{'database':0,'unnecessary_model_rerun':0},'persistence':{}}
    data=payload(request)
    if identity=='A10-PROCEDURES':
        import asyncio
        source='procedure_summary'
        initial=[payload(request,source=source,ids=[name]) for name in ('doc-a','doc-b')]
        initial[1]['summary_text']='Prior validated procedure from doc-b.'
        await repo.upsert_many_for_source(request.appointment_id,source,initial,allow_prune=True)
        lock=asyncio.Lock();commit=session.commit;rollback=session.rollback
        async def acquire(*args):await lock.acquire()
        async def commit_release():
            await commit()
            if lock.locked():lock.release()
        async def rollback_release():
            await rollback()
            if lock.locked():lock.release()
        repo._lock_scope=acquire;session.commit=commit_release;session.rollback=rollback_release
        await asyncio.gather(
            repo.upsert_many_for_source(request.appointment_id,source,[payload(request,state='partial',source=source,ids=['doc-a'])],allow_prune=False),
            repo.record_processing_failure(request.appointment_id,source,request.user_id,[{'source_id':'doc-b','error':'PARSE_FAILED'}]))
        keys=[repo._document_ids_key(row.summary_metadata) for row in session.rows]
        observed['persistence'].update(duplicate_rows=len(keys)-len(set(keys)),failed_source_rows_preserved=any(row.summary_metadata.get('source_document_ids')==['doc-b'] and initial[1]['summary_text'] in row.summary_text for row in session.rows))
        observed['pipeline_output']={'rows':[ConversationSummary.model_validate(row).model_dump(mode='json') for row in session.rows],'qualification':'Actual publication logic; simulated transaction lock, no database connection'}
        return observed
    if identity=='CANCEL-COMMIT':
        import asyncio
        entered=asyncio.Event();release=asyncio.Event();commit=session.commit
        async def delayed_commit():
            entered.set();await release.wait();await commit()
        session.commit=delayed_commit
        task=asyncio.create_task(repo.upsert(request.appointment_id,deepcopy(data)))
        await entered.wait();task.cancel();release.set()
        try:await task
        except asyncio.CancelledError:pass
        observed['persistence'].update(commit_state_reconciled=session.commits==1 and len(session.committed)==1 and session.committed[0][1]['summary_text']==data['summary_text'],duplicate_rows=max(0,len(session.rows)-1))
        observed['pipeline_output']={'commits':session.commits,'cancelled':task.cancelled()}
        return observed
    if identity=='A10-ORM':
        from src.app.db.objects.entities.conversation_summaries import ConversationSummaries
        table=ConversationSummaries.__table__
        unique_appointment=any(type(c).__name__=='UniqueConstraint' and [column.name for column in c.columns]==['appointment_id'] for c in table.constraints)
        observed['persistence'].update(ddl_calls=0,orm_allows_multiple_sources=not table.c.appointment_id.unique and not unique_appointment)
        return observed
    if identity=='A10-FIRSTWRITES':
        import asyncio
        # Simulated transaction lock boundary. The actual repository must acquire it
        # before lookup; this tests ordering, not PostgreSQL lock implementation.
        lock=asyncio.Lock();original_read=repo.get_by_appointment_id_and_source;commit=session.commit;rollback=session.rollback
        async def acquire(*args):await lock.acquire()
        async def read(*args):await asyncio.sleep(.005);return await original_read(*args)
        async def commit_release():
            await commit()
            if lock.locked():lock.release()
        async def rollback_release():
            await rollback()
            if lock.locked():lock.release()
        repo._lock_scope=acquire;repo.get_by_appointment_id_and_source=read;session.commit=commit_release;session.rollback=rollback_release
        await asyncio.gather(*(repo.upsert(request.appointment_id,deepcopy(data)) for _ in range(4)))
        observed['persistence']['duplicate_rows']=len(session.rows)-1
    else:
        commit=session.commit;ack_lost=[];post_commit_refresh=[];precommit_failure=[]
        async def commit_boundary():
            if identity=='ERROR-PERSISTRETRY' and not precommit_failure:
                precommit_failure.append(True)
                error=OSError('Synthetic transaction aborted before commit');error.orig=SimpleNamespace(sqlstate='40001');raise error
            await commit()
            if identity=='A19-ACK':ack_lost.append(True);raise OSError('Synthetic acknowledgement lost')
        async def refresh_boundary(row):
            if session.commits:
                post_commit_refresh.append(True);raise OSError('Synthetic refresh failure after commit')
        session.commit=commit_boundary;session.refresh=refresh_boundary
        row=await repo.upsert(request.appointment_id,deepcopy(data))
        committed=bool(session.committed) and session.committed[0][1]['summary_text']==data['summary_text']
        if identity=='A19-RESPONSE':
            try:ConversationSummary.model_validate({'id':'invalid-response'})
            except Exception:pass
        observed['persistence'].update(commit_state_reconciled=bool(ack_lost) and committed,duplicate_rows=max(0,len(session.rows)-1),committed_result_preserved=committed,failure_placeholder_overwrote_commit=bool(session.committed) and session.committed[0][1]['summary_text']!=data['summary_text'],unsafe_draft_saved=not committed,saved_once=session.commits==1)
    observed['pipeline_output']={'commits':session.commits,'rollbacks':session.rollbacks,'rows':[ConversationSummary.model_validate(r).model_dump(mode='json',by_alias=True) for r in session.rows]}
    return observed
