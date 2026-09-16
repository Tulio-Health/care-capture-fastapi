"""Verification truncation must never publish unchecked OCR. No network or database."""
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock
from src.app.services.document_ocr import transcribe_verified_image
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summary_runtime import WorkBudget, _current_budget
from src.app.core.settings import Settings


def response(content, finish='stop', refusal=None):
    return NS(choices=[NS(finish_reason=finish, message=NS(content=content, refusal=refusal))])


class OCRVerificationSafety(unittest.IsolatedAsyncioTestCase):
    def client(self, *verifications):
        transcription=response(json.dumps({'text':'Chest X-ray ordered. Not performed.', 'complete':True, 'unreadable_regions':[]}))
        create=AsyncMock(side_effect=[transcription,*verifications])
        return NS(chat=NS(completions=NS(create=create))),create

    async def test_complete_verification_uses_central_default_without_retry(self):
        client,create=self.client(response('{"matches":true,"issues":[]}'))
        text=await transcribe_verified_image(client,'mock','image',1)
        self.assertIn('Not performed',text)
        self.assertEqual(create.await_count,2)
        self.assertEqual(create.call_args.kwargs['max_tokens'],Settings.model_fields['DOCUMENT_OCR_VERIFICATION_OUTPUT_TOKENS'].default)

    async def test_truncation_retries_same_evidence_once_and_accepts_complete_verdict(self):
        client,create=self.client(response('{"matches":true', 'length'),response('{"matches":true,"issues":[]}'))
        await transcribe_verified_image(client,'mock','image',1)
        calls=create.call_args_list
        self.assertEqual([c.kwargs['max_tokens'] for c in calls[1:]],[2048,4096])
        self.assertEqual(calls[1].kwargs['messages'],calls[2].kwargs['messages'])

    async def test_second_truncation_withholds_text(self):
        client,create=self.client(response('{}','length'),response('{}','length'))
        with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        self.assertEqual(create.await_count,3)

    async def test_negative_filtered_refused_malformed_or_empty_never_retried(self):
        for verdict in [response('{"matches":false,"issues":["wrong value"]}'),response('{}','content_filter'),response('{}',refusal='refused'),response('broken'),NS(choices=[]),response('{"matches":true,"issues":["omission"]}')]:
            with self.subTest(verdict=verdict):
                client,create=self.client(verdict)
                with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
                self.assertEqual(create.await_count,2)

    async def test_truncated_positive_is_not_accepted_when_budget_prevents_larger_retry(self):
        client,create=self.client(response('{"matches":true,"issues":[]}','length'))
        token=_current_budget.set(WorkBudget(max_output_tokens=2048))
        try:
            with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        finally:_current_budget.reset(token)
        self.assertEqual(create.await_count,2)

    async def test_retry_respects_model_call_budget(self):
        client,create=self.client(response('{}','length'),response('{"matches":true,"issues":[]}'))
        token=_current_budget.set(WorkBudget(max_model_calls=2))
        try:
            with self.assertRaises(DocumentProcessingError):await transcribe_verified_image(client,'mock','image',1)
        finally:_current_budget.reset(token)
        self.assertEqual(create.await_count,2)

    async def test_custom_limits_are_used_and_bounded_by_output_budget(self):
        client,create=self.client(response('{}','length'),response('{"matches":true,"issues":[]}'))
        token=_current_budget.set(WorkBudget(max_output_tokens=3000))
        try:await transcribe_verified_image(client,'mock','image',1,verification_output_tokens=1500,verification_retry_output_tokens=4096)
        finally:_current_budget.reset(token)
        self.assertEqual([c.kwargs['max_tokens'] for c in create.call_args_list[1:]],[1500,3000])

if __name__=='__main__':unittest.main()
