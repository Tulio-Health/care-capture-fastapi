"""Real publication decisions with memory-only session boundaries; never SQL/DDL."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.app.db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from src.app.db.objects.entities.conversation_summaries import ConversationSummaries
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summary_outcomes import nonclinical_payload, outcome_metadata


class MemorySession:
    def __init__(self):
        self.rows = []
        self.commits = 0
        self.deleted = []
        self.rollbacks = 0
        self.committed = []
    def add(self, row):
        row.id = row.id or uuid4()
        row.created_at = row.created_at or datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        self.rows.append(row)
    async def execute(self, *args, **kwargs):
        raise AssertionError('QA must replace the database read/lock boundary; SQL is forbidden')
    async def flush(self): pass
    async def refresh(self, row): pass
    async def commit(self):
        self.commits += 1
        self.committed = [(row, deepcopy({k:v for k,v in row.__dict__.items() if not k.startswith('_sa_')})) for row in self.rows]
    async def rollback(self):
        self.rollbacks += 1
        self.rows[:] = [row for row, values in self.committed]
        for row, values in self.committed:
            for key,value in values.items(): setattr(row,key,deepcopy(value))
    async def delete(self, row): self.deleted.append(row); self.rows.remove(row)


def setup_repository():
    session = MemorySession()
    repository = ConversationSummariesRepository(session)
    repository._lock_scope = AsyncMock()
    async def get_one(appointment_id, source):
        return next((row for row in session.rows if row.appointment_id == appointment_id and (row.summary_metadata or {}).get('source') == source), None)
    async def get_many(appointment_id, source):
        return [row for row in session.rows if row.appointment_id == appointment_id and (row.summary_metadata or {}).get('source') == source]
    async def get_id(identity):
        return next((row for row in session.rows if row.id == identity), None)
    repository.get_by_id = get_id
    repository.get_by_appointment_id_and_source = get_one
    repository.get_all_by_appointment_id_and_source = get_many
    return repository, session


def payload(request, state='complete', source='attachment_summary', ids=None):
    value = nonclinical_payload(request, source)
    value.update(summary_text='Ultrasound ordered; not performed.', diagnoses=[{'official_diagnosis': 'Iron deficiency anemia', 'lay_explanation': ''}])
    value['summary_metadata'].update(outcome_metadata(state))
    if ids is not None: value['summary_metadata']['source_document_ids'] = ids
    return value


class PublicationSafety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.request = SimpleNamespace(appointment_id=uuid4(), user_id=uuid4())
        self.repository, self.session = setup_repository()
    async def save(self, data):
        return await self.repository.upsert(self.request.appointment_id, data)
    async def test_failed_refresh_preserves_validated_summary_and_displays_notice_once(self):
        row = await self.save(payload(self.request))
        diagnosis = deepcopy(row.diagnoses)
        failed = nonclinical_payload(self.request, 'attachment_summary', errors=[{'error':'PARSE_FAILED'}])
        for _ in range(2): await self.save(deepcopy(failed))
        self.assertEqual(row.diagnoses, diagnosis)
        self.assertEqual(row.summary_text.count('previous summary'), 1)
        self.assertEqual(row.summary_metadata['last_refresh_outcome']['processing_outcome'], 'unavailable')
        self.assertEqual(len(self.session.rows), 1)
    async def test_success_clears_refresh_failure_and_preserves_unrelated_metadata(self):
        initial = payload(self.request); initial['summary_metadata']['integration_tag'] = 'keep'
        row = await self.save(initial)
        await self.save(nonclinical_payload(self.request, 'attachment_summary'))
        await self.save(payload(self.request))
        self.assertNotIn('last_refresh_outcome', row.summary_metadata)
        self.assertEqual(row.summary_metadata['integration_tag'], 'keep')
        self.assertNotIn('previous summary', row.summary_text)
    async def test_invalid_previous_clinical_fields_cleared(self):
        initial = payload(self.request); initial['summary_metadata']['validation_status'] = 'failed'
        row = await self.save(initial)
        await self.save(nonclinical_payload(self.request, 'attachment_summary'))
        self.assertEqual(row.diagnoses, [])
        self.assertFalse(row.summary_metadata['is_clinical_summary'])
    async def test_old_attempt_cannot_overwrite_new(self):
        new = payload(self.request); new['summary_metadata']['attempt_started_at']='2026-09-16T12:00:00+00:00'
        row = await self.save(new)
        old = payload(self.request); old['summary_metadata']['attempt_started_at']='2026-09-16T11:00:00+00:00'; old['summary_text']='stale'
        await self.save(old)
        self.assertNotEqual(row.summary_text, 'stale')
    async def test_original_creator_preserved(self):
        row = await self.save(payload(self.request)); original = row.created_by
        update = payload(self.request); update['created_by'] = uuid4()
        await self.save(update)
        self.assertEqual(row.created_by, original)
    async def test_nonserializable_payload_rejected_before_commit(self):
        data = payload(self.request); data['summary_metadata']['bad'] = object()
        with self.assertRaises(DocumentProcessingError): await self.save(data)
        self.assertEqual(self.session.commits, 0)
    async def test_partial_procedure_attempt_cannot_prune(self):
        source='procedure_summary'
        rows=[payload(self.request, source=source, ids=[identity]) for identity in ['a','b']]
        await self.repository.upsert_many_for_source(self.request.appointment_id,source,rows,allow_prune=True)
        await self.repository.upsert_many_for_source(self.request.appointment_id,source,[payload(self.request, source=source, ids=['a'])],allow_prune=False)
        self.assertEqual(len(self.session.rows),2); self.assertEqual(self.session.deleted,[])
    async def test_successful_zero_event_result_prunes_only_its_source(self):
        await self.save(payload(self.request))
        await self.repository.upsert_many_for_source(self.request.appointment_id,'procedure_summary',[payload(self.request,source='procedure_summary',ids=['a'])],allow_prune=True)
        await self.repository.upsert_many_for_source(self.request.appointment_id,'procedure_summary',[],allow_prune=True,user_id=self.request.user_id)
        self.assertEqual(len(self.session.rows),1)
        self.assertEqual(self.session.rows[0].summary_metadata['source'],'attachment_summary')
    async def test_document_keys_cannot_collide_on_separator(self):
        key=self.repository._document_ids_key
        self.assertNotEqual(key({'source_document_ids':['a,b','c']}),key({'source_document_ids':['a','b,c']}))

if __name__ == '__main__': unittest.main()
