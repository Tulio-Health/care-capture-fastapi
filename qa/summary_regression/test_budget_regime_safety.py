"""Regime A budget-ceiling regressions with fake model boundaries; no paid API or DB.

Each fake boundary burns exactly one budget unit through the real
reserve_provider_request, mirroring the production hooked client (llm_factory), and the
judge stub burns its unit through the real model_call, mirroring clinical_grounding.

Case 1 (audit round5 SS4 case 1): happy path at N=40 completes; N+2=42 calls <= 64.
Case 2 (audit round5 SS4 case 2): boundary recovery at N=30 -- final audit rejects,
replays pass -- completes at exactly 2N+3=63 calls, pinning the recovery ceiling at the
crossover so any future extra call on the recovery path breaks here instead of silently
moving the production crossover.
Case 3 (audit round5 SS4 case 3, lands with the R13 fix): beyond the crossover at N=40 a
final-audit rejection fails closed on the judge's own verdict at N+2 calls, with the
replay skipped instead of burning to the 64-call budget wall.
"""
import json
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DocumentAttachment,
    DocumentSummary,
)
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.document_ingestion import mark_parsed
from src.app.services.summary_runtime import (
    WorkBudget,
    _current_budget,
    model_call,
    reserve_provider_request,
)


def _text(index):
    return f"Visit note {index}: cough documented. Rest advised."


def documents(count):
    return [
        mark_parsed(DocumentAttachment(
            file_path=f"qa://doc-{index}", content_type="text/plain",
            resource_id=f"doc-{index}", extracted_text=_text(index),
        ))
        for index in range(count)
    ]


async def _burn_one():
    # One budget unit per provider request -- exactly what the production httpx hook does.
    await reserve_provider_request(NS(content=json.dumps({"max_tokens": 16}).encode()))


def _source_id(prompt):
    marker = "Source ID: "
    start = prompt.index(marker) + len(marker)
    return prompt[start:prompt.index("\n", start)]


def chain_under_test():
    chain = AttachmentSummarizationChain()
    chain._model = object()

    async def extraction_run(prompt, **kwargs):
        await _burn_one()
        source_id = _source_id(prompt)
        index = int(source_id.split(":", 1)[0].split("-", 1)[1])
        text = _text(index)
        return NS(output=[DocumentSummary(
            source_document_id=source_id, source_document_title=f"doc-{index}",
            source_document_type="Visit note", evidence_quotes=[text],
            narrative_summary=text,
        )])

    async def synthesis_run(prompt, **kwargs):
        await _burn_one()
        return NS(output=AttachmentSummarizationResponse(
            clinical_summary="Documented visit.", documents_analyzed=0,
        ))

    chain._extraction_agent = NS(run=extraction_run)
    chain._synthesis_agent = NS(run=synthesis_run)
    return chain


class _JudgeStub:
    """Burns one budget unit per audit through the real model_call, like verify_grounding."""

    def __init__(self, verdict):
        self.calls = 0
        self._verdict = verdict

    async def __call__(self, model, source, candidate, *, scope="clinical_summary"):
        index = self.calls
        self.calls += 1
        async def judge_model_run():
            await _burn_one()
        await model_call(judge_model_run)
        failure = self._verdict(index)
        if failure is not None:
            raise failure


class BudgetRegimeSafety(unittest.IsolatedAsyncioTestCase):
    def budget(self):
        budget = WorkBudget(deadline=time.monotonic() + 300)
        token = _current_budget.set(budget)
        self.addCleanup(_current_budget.reset, token)
        return budget

    async def test_happy_path_40_batches_completes_within_budget(self):
        budget = self.budget()
        judge = _JudgeStub(lambda index: None)
        with patch("src.app.chains.attachment_summarization.chain.verify_grounding", new=judge):
            result = await chain_under_test().analyze({}, documents(40))
        self.assertEqual(result.documents_analyzed, 40)
        self.assertEqual(judge.calls, 1)
        self.assertEqual(budget.provider_requests, 42)  # N + 2
        self.assertLessEqual(budget.provider_requests, budget.max_model_calls)

    async def test_boundary_recovery_30_batches_costs_exactly_63_calls(self):
        budget = self.budget()
        judge = _JudgeStub(lambda index: DocumentProcessingError("GROUNDING_VALIDATION_FAILED") if index == 0 else None)
        with patch("src.app.chains.attachment_summarization.chain.verify_grounding", new=judge):
            result = await chain_under_test().analyze({}, documents(30))
        self.assertEqual(result.documents_analyzed, 30)
        self.assertEqual(judge.calls, 32)  # rejected single audit + N+1 passing replays
        self.assertEqual(budget.provider_requests, 63)  # 2N + 3, the true recovery ceiling


if __name__ == "__main__":
    unittest.main()
