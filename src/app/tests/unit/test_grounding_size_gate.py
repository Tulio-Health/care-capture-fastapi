"""Steps 0-2 (round9-revision.md section 10): the measured size check. Pins section 11's
minimum test plan for those steps -- the byte-measurement sizer (Fix 1, section 4), the four
call-site semantics (Fix 2, section 5), and the constant-30 `_judge_timeout_s` scoping
(section 8.4(a), Step-2 item 10).

STEP 4 (.research/fastapi-grounding-check-token-and-model/step4-corrected-scope.md): the
large-input judge mode -- GROUNDING_SANITY_MAX_CHARACTERS raised to 600_000,
WorkBudget.max_judge_input_bytes = 700_000, and the x2 dispatch reservation at chain.py's
site-2 final audit -- is now IN SCOPE and exercised for real by TestStep4CorrectedConstants,
TestStep4LargeInputJudgeMode and TestStep4DispatchScoping below: they construct real bodies
in the 500,000-700,000 B band and drive them end to end through grounding_request_fits /
_judge_timeout_s / reserve_input_bytes, so the large-body assertions in
TestJudgeTimeoutScoping are no longer merely correct-if-reached -- they are reached, here.

Section 11 items covered by file location:
  - test 1 (envelope pin): TestEnvelopePin
  - test 2 (single payload/builder): TestSharedPayloadAndBuilder
  - test 3 (break-even behaviour): TestBreakEvenBehaviour
  - test 4 (the four semantics): TestFourSemantics
    (4a/4b1 are already pinned by test_pr12b_validation_consolidation.py's
    test_regime_b_oversized_skip_emits_final_audit_skipped_record and
    test_verify_final_oversized_single_audit_emits_single_audit_skipped_record -- not
    duplicated here)
  - test 5 (regime split immovable): src/app/tests/unit/test_regime_split_chars.py
  - test 6 (prompt identity): TestPromptIdentity
  - test 7 (unbudgeted path untouched): TestUnbudgetedPath
  - test 8 (:891 routing): TestSite4AccessorRouting
  - test 9 (bonus-audit degradation): TestBonusAuditDegradation
  - test 10 (byte reservation under concurrency): TestBudgetedReservationPath
  - test 11 (dispatch multiplier, STEP 4): TestStep4DispatchScoping
  - test 12(c)/(d)/(e) (deadline clamp confinement, required by Step-2 item 10):
    TestJudgeTimeoutScoping
  - step4-corrected-scope.md section 12 acceptance items 1-3 (corrected constants, margin,
    non-empty band) and direct clamp-reachability evidence: TestStep4CorrectedConstants,
    TestStep4LargeInputJudgeMode
"""

import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import AttachmentSummarizationResponse
from src.app.services import clinical_grounding
from src.app.services.clinical_grounding import (
    GroundingFit,
    GroundingVerdict,
    verify_grounding,
)
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.summary_runtime import (
    WorkBudget,
    _current_budget,
    _UNBUDGETED,
    reserve_input_bytes,
    release_input_bytes,
    reserve_provider_request,
)

import json


def _settings_patches(run):
    """The three-patch combination test_clinical_grounding.py already established for
    exercising verify_grounding without a real model call: settings, the pydantic_ai model
    factory, and the Agent constructor itself."""
    return (
        patch(
            "src.app.core.settings.get_settings",
            return_value=NS(DOCUMENT_VERIFICATION_MODEL="mock"),
        ),
        patch(
            "src.app.common.llm_factory.get_pydantic_ai_model", return_value=object()
        ),
        patch("pydantic_ai.Agent", return_value=NS(run=run)),
    )


def _passing_run():
    return AsyncMock(
        return_value=NS(output=GroundingVerdict(supported=True, issues=[]))
    )


# ---------------------------------------------------------------------------
# Test 1: envelope pin
# ---------------------------------------------------------------------------


class TestEnvelopePin:
    @pytest.mark.asyncio
    async def test_judge_request_bytes_is_never_optimistic_and_never_wildly_pessimistic(
        self,
    ):
        """Capture a REAL judge request through httpx.MockTransport (real pydantic_ai 1.30.1 +
        openai SDK, no network egress) and assert judge_request_bytes(user_message) >= the real
        wire text_bound reserve_provider_request would measure, with a gap < 2,048 bytes. The
        one test that catches SDK request-shape drift; also the invariant that keeps section
        4.6's prepaid job-wall leg unreachable in practice (round-6 MINOR-5)."""
        captured = {}

        async def transport(request):
            captured["content"] = request.content
            body = json.loads(request.content)
            tool = body["tools"][0]["function"]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "arguments": json.dumps({"supported": True, "issues": []}),
                        },
                    }
                ],
            }
            return httpx.Response(
                200,
                json={
                    "id": "mock",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [
                        {"index": 0, "message": message, "finish_reason": "tool_calls"}
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )

        client = AsyncOpenAI(
            api_key="test",
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(transport), trust_env=False
            ),
        )
        model = OpenAIChatModel(
            "gpt-4.1-mini", provider=OpenAIProvider(openai_client=client)
        )
        agent = Agent(
            model,
            output_type=GroundingVerdict,
            retries=0,
            model_settings=ModelSettings(temperature=0, max_tokens=1500, timeout=30),
            system_prompt=clinical_grounding._JUDGE_SYSTEM_PROMPT,
        )
        source = (
            "Patient denies any medication use. No active prescriptions on file." * 200
        )
        payload = {
            "clinical_findings": ["stable, no new complaints"],
            "procedures_performed": [],
        }
        user_message = clinical_grounding._build_judge_message(
            source, payload, "clinical_summary"
        )

        result = await agent.run(user_message)
        assert result.output.supported is True

        real_body = json.loads(captured["content"])

        def text_only(item):
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    return {"type": "image_url"}
                return {key: text_only(value) for key, value in item.items()}
            if isinstance(item, list):
                return [text_only(value) for value in item]
            return item

        text_bound = len(json.dumps(text_only(real_body), ensure_ascii=False).encode())
        predicted = clinical_grounding.judge_request_bytes(user_message)

        assert predicted >= text_bound
        assert predicted - text_bound < 2_048


# ---------------------------------------------------------------------------
# Test 2: single payload, single builder
# ---------------------------------------------------------------------------


class TestSharedPayloadAndBuilder:
    @pytest.mark.asyncio
    async def test_verify_grounding_and_predicate_produce_byte_identical_messages(
        self, monkeypatch
    ):
        """round-6 MINOR-2: monkeypatch _judge_payload/_build_judge_message to recording
        wrappers; one grounding_request_fits call followed by one verify_grounding call on the
        SAME (source, output) must produce byte-identical user_message strings, and a payload
        carrying `procedures` with `status` keys must be split into procedures_<status> in
        BOTH."""
        payload_calls = []
        message_calls = []
        real_payload = clinical_grounding._judge_payload
        real_message = clinical_grounding._build_judge_message

        def recording_payload(output):
            result = real_payload(output)
            payload_calls.append(result)
            return result

        def recording_message(source, payload, scope):
            result = real_message(source, payload, scope)
            message_calls.append(result)
            return result

        monkeypatch.setattr(clinical_grounding, "_judge_payload", recording_payload)
        monkeypatch.setattr(
            clinical_grounding, "_build_judge_message", recording_message
        )

        class Candidate:
            def model_dump(self):
                return {
                    "clinical_summary": "x",
                    "procedures": [
                        {
                            "description": "Biopsy",
                            "status": "performed",
                            "source_quote": "q",
                        },
                        {
                            "description": "MRI",
                            "status": "ordered",
                            "source_quote": "q2",
                        },
                    ],
                }

        source = "some source text"
        candidate = Candidate()

        fit = clinical_grounding.grounding_request_fits(source, candidate)
        assert fit.fits

        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        with p1, p2, p3:
            await verify_grounding(None, source, candidate)

        assert len(message_calls) == 2
        assert message_calls[0] == message_calls[1]
        assert len(payload_calls) == 2
        for payload in payload_calls:
            assert "procedures" not in payload
            assert [
                item["description"] for item in payload["procedures_performed"]
            ] == ["Biopsy"]
            assert [item["description"] for item in payload["procedures_ordered"]] == [
                "MRI"
            ]
            assert payload["procedures_not_stated"] == []


# ---------------------------------------------------------------------------
# Test 3: break-even behaviour
# ---------------------------------------------------------------------------


class TestBreakEvenBehaviour:
    @pytest.mark.parametrize("filler_char", ["x", '"'])
    def test_grounding_request_fits_flips_exactly_once_by_size(self, filler_char):
        """Parametrize over a plain-ASCII filler and an escape-heavy (JSON-shaped) filler,
        bracketing the break-even under an active budget; assert truthy below and falsy above,
        and that GroundingFit.reason is exactly one section-8.6 vocabulary value (never a
        compound) on the falsy side."""
        candidate = {"clinical_summary": "y"}
        budget = WorkBudget(deadline=0)
        token = _current_budget.set(budget)
        try:
            # STEP 4: hi must clear both GROUNDING_SANITY_MAX_CHARACTERS (600_000) and
            # WorkBudget's default max_judge_input_bytes (700_000) with margin.
            lo, hi = 1, 900_000
            assert clinical_grounding.grounding_request_fits(
                filler_char * lo, candidate
            ).fits
            assert not clinical_grounding.grounding_request_fits(
                filler_char * hi, candidate
            ).fits
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if clinical_grounding.grounding_request_fits(
                    filler_char * mid, candidate
                ).fits:
                    lo = mid
                else:
                    hi = mid
            below = clinical_grounding.grounding_request_fits(
                filler_char * lo, candidate
            )
            above = clinical_grounding.grounding_request_fits(
                filler_char * hi, candidate
            )
            assert below.fits and below.reason is None
            assert not above.fits
            assert above.reason in {
                "sanity_bound",
                "call_byte_ceiling",
                "job_byte_budget",
                "latency_gate",
            }
        finally:
            _current_budget.reset(token)

    @pytest.mark.asyncio
    async def test_a_falsy_predicate_never_reaches_model_call(self, monkeypatch):
        async def fail_if_called(operation, *args, **kwargs):
            raise AssertionError(
                "model_call must never run when the predicate is falsy"
            )

        monkeypatch.setattr(clinical_grounding, "model_call", fail_if_called)
        oversized_source = "x" * (
            clinical_grounding.GROUNDING_SANITY_MAX_CHARACTERS + 1
        )
        candidate = {"clinical_summary": "y"}

        fit = clinical_grounding.grounding_request_fits(oversized_source, candidate)
        assert not fit.fits

        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        with p1, p2, p3:
            with pytest.raises(DocumentProcessingError) as excinfo:
                await verify_grounding(None, oversized_source, candidate)
        assert excinfo.value.reason_code == "VALIDATION_BUDGET_EXCEEDED"
        run.assert_not_called()  # the sanity bound rejects before Agent/model_call is ever reached


# ---------------------------------------------------------------------------
# Test 4: the four semantics -- items b2/b3/c/d/e/f (a and b1 are pinned in
# test_pr12b_validation_consolidation.py, see the module docstring above)
# ---------------------------------------------------------------------------


class TestFourSemantics:
    @pytest.mark.asyncio
    async def test_4b2_oversized_entrance_with_empty_audits_raises_validation_budget_exceeded(
        self, monkeypatch
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=False, reason="sanity_bound", body_bytes=999_999
            ),
        )
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})
        token = chain._deferred_grounding.set(
            []
        )  # non-None (Regime A) but genuinely empty
        try:
            with pytest.raises(DocumentProcessingError) as excinfo:
                await chain_instance._verify_final(
                    "source", candidate, accepted_ids=set()
                )
        finally:
            chain._deferred_grounding.reset(token)
        assert excinfo.value.reason_code == "VALIDATION_BUDGET_EXCEEDED"

    @pytest.mark.asyncio
    async def test_4b3_oversized_entrance_insufficient_headroom_raises_and_never_launches_replay(
        self, monkeypatch
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=False, reason="sanity_bound", body_bytes=999_999
            ),
        )
        monkeypatch.setattr(
            chain, "model_call_headroom", lambda: 0
        )  # below len(surviving_audits)
        calls = []

        async def fake_verify_grounding(model, evidence, output):
            calls.append(evidence)

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        output_a = NS(source_document_id="doc-a")
        audits = [("extraction", "evidence-a", output_a)]
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})
        token = chain._deferred_grounding.set(audits)
        try:
            with pytest.raises(DocumentProcessingError) as excinfo:
                await chain_instance._verify_final(
                    "source", candidate, accepted_ids={"doc-a"}
                )
        finally:
            chain._deferred_grounding.reset(token)
        assert excinfo.value.reason_code == "MODEL_CALL_BUDGET_EXCEEDED"
        assert (
            calls == []
        )  # the replay never launched -- oversized entrance, no rejection in hand

    @pytest.mark.asyncio
    async def test_4c_unbounded_call_site_propagates_grounding_request_too_large(self):
        """sites 5/7/8 (fhir_analysis, transcript_summarization, translation): none of them add
        any special catch/degrade around verify_grounding -- exercised here directly, since all
        budgeted sites share one model, one client, one hook, one wall (round9-revision.md
        section 7.2), so the byte arithmetic and the raise are identical regardless of caller.
        """
        budget = WorkBudget(
            deadline=0, max_call_input_bytes=1, max_judge_input_bytes=1
        )  # any real body exceeds this -- STEP 4: _judge_call_limit prefers
        # max_judge_input_bytes over max_call_input_bytes, so both must be constrained
        token = _current_budget.set(budget)
        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        try:
            with p1, p2, p3:
                with pytest.raises(DocumentProcessingError) as excinfo:
                    await verify_grounding(
                        None, "some source", {"clinical_summary": "x"}
                    )
        finally:
            _current_budget.reset(token)
        assert excinfo.value.reason_code == "GROUNDING_REQUEST_TOO_LARGE"
        run.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_rejection", [True, False])
    async def test_4d_full_skip_fails_closed(self, monkeypatch, caplog, with_rejection):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})

        def fits_stub(source, output, **kw):
            if output is candidate:
                return GroundingFit(
                    fits=with_rejection,
                    reason=None if with_rejection else "sanity_bound",
                    body_bytes=1,
                )
            return GroundingFit(
                fits=False, reason="sanity_bound", body_bytes=1
            )  # every snapshot skipped

        monkeypatch.setattr(chain, "grounding_request_fits", fits_stub)
        rejection_exc = DocumentProcessingError("GROUNDING_VALIDATION_FAILED")

        async def fake_verify_grounding(model, source_or_evidence, output):
            if with_rejection and output is candidate:
                raise rejection_exc
            raise AssertionError(
                "verify_grounding must never run for a skipped replay snapshot"
            )

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        output_a = NS(source_document_id="doc-a")
        output_b = NS(source_document_id="doc-b")
        audits = [
            ("extraction", "evidence-a", output_a),
            ("synthesis", "evidence-b", output_b),
        ]
        token = chain._deferred_grounding.set(audits)
        try:
            with caplog.at_level("WARNING"):
                with pytest.raises(DocumentProcessingError) as excinfo:
                    await chain_instance._verify_final(
                        "source", candidate, accepted_ids={"doc-a"}
                    )
        finally:
            chain._deferred_grounding.reset(token)

        if with_rejection:
            assert (
                excinfo.value is rejection_exc
            )  # the SAME exception object is re-raised
        else:
            assert excinfo.value.reason_code == "VALIDATION_BUDGET_EXCEEDED"
        incomplete = [
            r.message
            for r in caplog.records
            if r.message.startswith("replay_incomplete")
        ]
        assert len(incomplete) == 1
        assert "skipped=2 total=2" in incomplete[0]

    @pytest.mark.asyncio
    async def test_4e_partial_skip_fails_closed_on_held_rejection(
        self, monkeypatch, caplog
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})
        skip_evidence = "evidence-3"

        def fits_stub(source, output, **kw):
            if output is candidate:
                return GroundingFit(fits=True, reason=None, body_bytes=1)
            if source == skip_evidence:
                return GroundingFit(
                    fits=False, reason="call_byte_ceiling", body_bytes=1
                )
            return GroundingFit(fits=True, reason=None, body_bytes=1)

        monkeypatch.setattr(chain, "grounding_request_fits", fits_stub)
        rejection_exc = DocumentProcessingError("GROUNDING_VALIDATION_FAILED")
        seen = []

        async def fake_verify_grounding(model, source_or_evidence, output):
            if output is candidate:
                raise rejection_exc
            seen.append(source_or_evidence)

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        outputs = [NS(source_document_id=f"doc-{i}") for i in range(6)]
        audits = [("extraction", f"evidence-{i}", outputs[i]) for i in range(6)]
        token = chain._deferred_grounding.set(audits)
        try:
            with caplog.at_level("WARNING"):
                with pytest.raises(DocumentProcessingError) as excinfo:
                    await chain_instance._verify_final(
                        "source",
                        candidate,
                        accepted_ids={f"doc-{i}" for i in range(6)},
                    )
        finally:
            chain._deferred_grounding.reset(token)

        assert (
            excinfo.value is rejection_exc
        )  # a partial replay is NOT a pass -- section 5.4.2
        assert sorted(seen) == [
            f"evidence-{i}" for i in range(6) if f"evidence-{i}" != skip_evidence
        ]
        assert skip_evidence not in seen
        incomplete = [
            r.message
            for r in caplog.records
            if r.message.startswith("replay_incomplete")
        ]
        assert len(incomplete) == 1
        assert "skipped=1 total=6" in incomplete[0]
        skip_records = [
            r.message
            for r in caplog.records
            if r.message.startswith("replay_audit_skipped:")
        ]
        assert len(skip_records) == 1

    @pytest.mark.asyncio
    async def test_4f_empty_surviving_set_is_unreachable_defense_in_depth(
        self, monkeypatch
    ):
        """section 5.4.3(iii): fabricate an audits list whose single entry is filtered out by
        accepted_ids entirely -- unreachable through the real pipeline (a synthesis snapshot
        always survives that filter), but the `not results` guard must still fail closed if a
        future refactor ever makes that untrue. No predicate mocking needed: the real
        grounding_request_fits fits this tiny content."""
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})
        rejection_exc = DocumentProcessingError("GROUNDING_VALIDATION_FAILED")

        async def fake_verify_grounding(model, source_or_evidence, output):
            if output is candidate:
                raise rejection_exc
            raise AssertionError(
                "no replay snapshot should ever run: the surviving set is empty"
            )

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        output_a = NS(source_document_id="doc-a")
        audits = [
            ("extraction", "evidence-a", output_a)
        ]  # doc-a not in accepted_ids -> filtered out
        token = chain._deferred_grounding.set(audits)
        try:
            with pytest.raises(DocumentProcessingError) as excinfo:
                await chain_instance._verify_final(
                    "source", candidate, accepted_ids=set()
                )
        finally:
            chain._deferred_grounding.reset(token)
        assert excinfo.value is rejection_exc


# ---------------------------------------------------------------------------
# Test 6: prompt identity
# ---------------------------------------------------------------------------


class TestPromptIdentity:
    @pytest.mark.asyncio
    async def test_agent_is_built_with_the_same_object_the_sizer_measures(self):
        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        with p1, p2, patch("pydantic_ai.Agent", return_value=NS(run=run)) as agent_cls:
            await verify_grounding(None, "source text", {"clinical_summary": "x"})
        assert (
            agent_cls.call_args.kwargs["system_prompt"]
            is clinical_grounding._JUDGE_SYSTEM_PROMPT
        )


# ---------------------------------------------------------------------------
# Test 7: unbudgeted path untouched, not crashing
# ---------------------------------------------------------------------------


class TestUnbudgetedPath:
    def test_release_input_bytes_is_a_noop_for_unbudgeted_and_none_tokens(self):
        assert _current_budget.get() is None
        token = reserve_input_bytes(None, 1_000, 1)
        assert token is _UNBUDGETED
        release_input_bytes(None, token)  # must not raise
        release_input_bytes(None, None)  # must not raise

    def test_grounding_request_fits_skips_the_byte_check_when_unbudgeted(self):
        """A quote-heavy source whose escaped wire body would exceed a BUDGETED
        max_call_input_bytes must still fit when no budget is active -- only the sanity bound
        applies on the unbudgeted path (round-4 MAJOR-4)."""
        assert _current_budget.get() is None
        source = '"' * 150_000  # comfortably under the 600,000-char sanity bound
        candidate = {"clinical_summary": "x"}
        fit = clinical_grounding.grounding_request_fits(source, candidate)
        assert fit.fits
        assert (
            fit.body_bytes > WorkBudget().max_call_input_bytes
        )  # would fail a BUDGETED call

    @pytest.mark.asyncio
    async def test_verify_grounding_completes_without_typeerror_when_unbudgeted(self):
        """This is the test that would have caught round-6 MAJOR-2: a bare release on an
        unguarded reserve raised TypeError on every unbudgeted grounding call in a prior
        draft."""
        assert _current_budget.get() is None
        source = '"' * 150_000
        candidate = {"clinical_summary": "x"}
        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        with p1, p2, p3:
            await verify_grounding(None, source, candidate)  # must not raise TypeError
        run.assert_awaited_once()

    def test_judge_timeout_s_unbudgeted_ordinary_and_large_bodies(self):
        assert _current_budget.get() is None
        assert (
            clinical_grounding._judge_timeout_s(80_000)
            == clinical_grounding._JUDGE_TIMEOUT_S
        )
        # Large-body branch: remaining_seconds(default) returns `default` unchanged when there
        # is no budget/deadline, so the unbudgeted path gets exactly _JUDGE_LARGE_TIMEOUT_S and
        # never the gate.
        assert (
            clinical_grounding._judge_timeout_s(
                clinical_grounding._LARGE_JUDGE_BODY_BYTES + 1
            )
            == clinical_grounding._JUDGE_LARGE_TIMEOUT_S
        )


# ---------------------------------------------------------------------------
# Test 7b (MAJOR-2, implementation-redteam-1.md): the budgeted reservation path.
# TestUnbudgetedPath above only exercises `budget is None`; these prove the SAME
# reserve_input_bytes/release_input_bytes pair is leak-free with an ACTIVE WorkBudget --
# the arithmetic the red-team verified by hand with a throwaway probe (reserve -> 2
# dispatches -> release ends at reserved=0, upper=2x text_bound; a refused reservation
# leaves the budget at 0) reproduced here as a real, committed test.
# ---------------------------------------------------------------------------


class TestBudgetedReservationPath:
    @pytest.mark.asyncio
    async def test_reserve_two_dispatches_release_ends_at_zero_reserved_and_upper_bound_charged_twice(
        self,
    ):
        budget = WorkBudget()
        cb_token = _current_budget.set(budget)
        try:
            body = {
                "messages": [{"role": "user", "content": "y" * 5_000}],
                "max_tokens": 100,
            }
            # Same transform reserve_provider_request applies internally: text_only is the
            # identity map for a body with no image_url content, so this IS the real charge
            # dispatch will measure, not an approximation of it.
            text_bound = len(json.dumps(body, ensure_ascii=False).encode())
            margin = 250
            predicted = text_bound + margin

            token = reserve_input_bytes(budget, predicted, 1)
            assert token is not None and token is not _UNBUDGETED
            assert budget.reserved_input_bytes == predicted

            request = NS(content=json.dumps(body).encode())
            await reserve_provider_request(request)  # dispatch 1
            assert budget.reserved_input_bytes == margin
            assert budget.input_upper_bound_bytes == text_bound
            assert budget.provider_requests == 1

            await reserve_provider_request(request)  # dispatch 2 (simulated transient retry)
            assert budget.reserved_input_bytes == 0
            assert budget.input_upper_bound_bytes == 2 * text_bound
            assert budget.provider_requests == 2

            release_input_bytes(budget, token)
            assert budget.reserved_input_bytes == 0  # no leak: nothing left to refund
            assert (
                budget.input_upper_bound_bytes == 2 * text_bound
            )  # release only refunds `reserved`, it never touches the real charge
        finally:
            _current_budget.reset(cb_token)

    def test_reservation_exceeding_job_headroom_is_refused_and_charges_nothing(self):
        budget = WorkBudget(max_input_bytes_per_job=100)
        token = reserve_input_bytes(budget, 1_000, 1)
        assert token is None
        assert budget.reserved_input_bytes == 0  # refused: no partial charge, no leak

    @pytest.mark.asyncio
    async def test_verify_grounding_raises_grounding_request_too_large_before_any_dispatch_when_job_wall_is_full(
        self,
    ):
        budget = WorkBudget(max_input_bytes_per_job=1)
        cb_token = _current_budget.set(budget)
        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)
        try:
            with p1, p2, p3:
                with pytest.raises(DocumentProcessingError) as excinfo:
                    await verify_grounding(None, "source", {"clinical_summary": "x"})
            assert excinfo.value.reason_code == "GROUNDING_REQUEST_TOO_LARGE"
            run.assert_not_called()  # refused before the model was ever dispatched
            assert budget.reserved_input_bytes == 0  # no leak on the refusal path
        finally:
            _current_budget.reset(cb_token)

    def test_grounding_request_fits_reports_job_byte_budget_reason_when_job_wall_is_full(
        self,
    ):
        budget = WorkBudget(max_input_bytes_per_job=1)
        cb_token = _current_budget.set(budget)
        try:
            fit = clinical_grounding.grounding_request_fits(
                "source", {"clinical_summary": "x"}
            )
            assert not fit.fits
            assert fit.reason == "job_byte_budget"
        finally:
            _current_budget.reset(cb_token)


# ---------------------------------------------------------------------------
# Test 8: :891-equivalent accessor routing
# ---------------------------------------------------------------------------


class TestSite4AccessorRouting:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reason_code,expected_calls",
        [
            # :891 widened set -- immediate raise, the replay never launches.
            ("MODEL_CALL_BUDGET_EXCEEDED", ["source"]),
            ("GROUNDING_REQUEST_TOO_LARGE", ["source"]),
            # Falls through to the replay. _audit_once_retried's own retry-eligible set is
            # {CLINICAL_EVIDENCE_FAILED, MODEL_OUTPUT_INVALID} (chain.py, unrelated to this
            # accessor), so a CLINICAL_EVIDENCE_FAILED-shaped rejection is retried once inside
            # the replay too, before the second raise propagates.
            ("CLINICAL_EVIDENCE_FAILED", ["source", "evidence-a", "evidence-a"]),
            # VALIDATION_BUDGET_EXCEEDED canonicalizes to RESOURCE_LIMIT_EXCEEDED, which is NOT
            # in _audit_once_retried's retry-eligible set, so the replay raises immediately on
            # its first (only) attempt.
            ("VALIDATION_BUDGET_EXCEEDED", ["source", "evidence-a"]),
        ],
    )
    async def test_site4_accessor_routes_on_reason_code(
        self, monkeypatch, reason_code, expected_calls
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})
        calls = []

        async def fake_verify_grounding(model, source_or_evidence, output):
            calls.append(source_or_evidence)
            raise DocumentProcessingError(reason_code)

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=True, reason=None, body_bytes=1
            ),
        )
        output_a = NS(source_document_id="doc-a")
        audits = [("extraction", "evidence-a", output_a)]
        token = chain._deferred_grounding.set(audits)
        try:
            with pytest.raises(DocumentProcessingError):
                await chain_instance._verify_final(
                    "source", candidate, accepted_ids={"doc-a"}
                )
        finally:
            chain._deferred_grounding.reset(token)

        assert calls == expected_calls


# ---------------------------------------------------------------------------
# Test 9: bonus-audit degradation
# ---------------------------------------------------------------------------


class TestBonusAuditDegradation:
    @pytest.mark.asyncio
    async def test_model_timeout_degrades_to_a_recorded_skip_and_publishes(
        self, monkeypatch, caplog
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=True, reason=None, body_bytes=1
            ),
        )
        calls = []

        async def fake_verify_grounding(model, source, output, **kwargs):
            calls.append(1)
            raise DocumentProcessingError("MODEL_TIMEOUT")

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        response = AttachmentSummarizationResponse(
            clinical_summary="x", documents_analyzed=1
        )
        token = chain._deferred_grounding.set(None)  # Regime B
        try:
            with caplog.at_level("WARNING"):
                await chain_instance._verify_final_with_retry(
                    "source", response, encounter_id="enc-1"
                )
        finally:
            chain._deferred_grounding.reset(token)
        assert (
            len(calls) == 1
        )  # degrades on the FIRST failure -- no retry for a timeout
        skip_records = [
            r.message
            for r in caplog.records
            if r.message.startswith("final_audit_skipped:")
        ]
        assert len(skip_records) == 1
        assert skip_records[0].startswith("final_audit_skipped:judge_timeout")

    @pytest.mark.asyncio
    async def test_model_rate_limited_degrades_to_a_recorded_skip_and_publishes(
        self, monkeypatch, caplog
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=True, reason=None, body_bytes=1
            ),
        )
        calls = []

        async def fake_verify_grounding(model, source, output, **kwargs):
            calls.append(1)
            raise DocumentProcessingError("MODEL_RATE_LIMITED")

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        response = AttachmentSummarizationResponse(
            clinical_summary="x", documents_analyzed=1
        )
        token = chain._deferred_grounding.set(None)  # Regime B
        try:
            with caplog.at_level("WARNING"):
                await chain_instance._verify_final_with_retry(
                    "source", response, encounter_id="enc-1"
                )
        finally:
            chain._deferred_grounding.reset(token)
        assert (
            len(calls) == 1
        )  # degrades on the FIRST failure -- no retry for a rate limit
        skip_records = [
            r.message
            for r in caplog.records
            if r.message.startswith("final_audit_skipped:")
        ]
        assert len(skip_records) == 1
        assert skip_records[0].startswith("final_audit_skipped:judge_rate_limited")

    @pytest.mark.asyncio
    async def test_clinical_evidence_failed_on_retry_still_raises(self, monkeypatch):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=True, reason=None, body_bytes=1
            ),
        )
        failure = DocumentProcessingError("GROUNDING_VALIDATION_FAILED")
        calls = AsyncMock(side_effect=[failure, failure])
        monkeypatch.setattr(chain, "verify_grounding", calls)
        response = AttachmentSummarizationResponse(
            clinical_summary="x", documents_analyzed=1
        )
        token = chain._deferred_grounding.set(None)
        try:
            with pytest.raises(DocumentProcessingError):
                await chain_instance._verify_final_with_retry("source", response)
        finally:
            chain._deferred_grounding.reset(token)
        assert (
            calls.await_count == 2
        )  # the retry DID run, and a real rejection fails closed

    @pytest.mark.asyncio
    async def test_latency_gate_produces_a_recorded_skip_and_publishes(
        self, monkeypatch, caplog
    ):
        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        monkeypatch.setattr(
            chain,
            "grounding_request_fits",
            lambda source, output, **kw: GroundingFit(
                fits=True, reason=None, body_bytes=1
            ),
        )

        async def fake_verify_grounding(model, source, output, **kwargs):
            raise DocumentProcessingError("GROUNDING_LATENCY_GATE")

        monkeypatch.setattr(chain, "verify_grounding", fake_verify_grounding)
        response = AttachmentSummarizationResponse(
            clinical_summary="x", documents_analyzed=1
        )
        token = chain._deferred_grounding.set(None)
        try:
            with caplog.at_level("WARNING"):
                await chain_instance._verify_final_with_retry("source", response)
        finally:
            chain._deferred_grounding.reset(token)
        skip_records = [
            r.message
            for r in caplog.records
            if r.message.startswith("final_audit_skipped:")
        ]
        assert len(skip_records) == 1
        assert skip_records[0].startswith("final_audit_skipped:latency_gate")


# ---------------------------------------------------------------------------
# Test 12(c)/(d)/(e): _judge_timeout_s scoping (Step-2 item 10's explicit requirement)
# ---------------------------------------------------------------------------


class TestJudgeTimeoutScoping:
    @pytest.mark.parametrize("remaining_s", [5, 11, 15, 20, 30, 50, 71, 119])
    def test_12c_ordinary_bodies_are_never_clamped(self, remaining_s):
        """Under round-7's defective shape this would return 0.00/0.00/2.00/4.50/9.50/19.50 at
        the first six of these remaining-clock values. Assert the return is 30.0 EXACTLY, not
        merely that it does not raise."""
        budget = WorkBudget(deadline=time.monotonic() + remaining_s)
        token = _current_budget.set(budget)
        try:
            assert (
                clinical_grounding._judge_timeout_s(80_000)
                == clinical_grounding._JUDGE_TIMEOUT_S
                == 30
            )
        finally:
            _current_budget.reset(token)

    def test_12d_largest_regime_a_judge_body_is_below_the_large_body_threshold(self):
        """Pins sections 5.5 and 5.4.3(iv), and confirms Step-2 item 10's own claim: no call
        site in Steps 0-2 can build a body over _LARGE_JUDGE_BODY_BYTES. Built from a source of
        exactly REGIME_SPLIT_CHARS chars plus a maximal (100,000-char) candidate. If
        REGIME_SPLIT_CHARS or the synthesis-records 100,000-char gate is ever raised, this test
        fails rather than the reasoning silently expiring."""
        source = "x" * chain.REGIME_SPLIT_CHARS
        candidate = {"clinical_summary": "y" * 100_000}
        payload = clinical_grounding._judge_payload(candidate)
        user_message = clinical_grounding._build_judge_message(
            source, payload, "clinical_summary"
        )
        body_bytes = clinical_grounding.judge_request_bytes(user_message)
        assert body_bytes < clinical_grounding._LARGE_JUDGE_BODY_BYTES

    @pytest.mark.parametrize(
        "body_bytes", [0, 100_000, 500_000, 500_001, 600_000, 2_000_000]
    )
    @pytest.mark.parametrize("remaining_s", [0, 5, 11, 15, 20, 30, 50, 71, 90, 119])
    def test_12e_never_returns_an_unusably_short_timeout(self, body_bytes, remaining_s):
        budget = WorkBudget(deadline=time.monotonic() + remaining_s)
        token = _current_budget.set(budget)
        try:
            try:
                result = clinical_grounding._judge_timeout_s(body_bytes)
            except DocumentProcessingError as exc:
                assert exc.reason_code == "GROUNDING_LATENCY_GATE"
            else:
                assert result >= clinical_grounding._JUDGE_MIN_LARGE_TIMEOUT_S
        finally:
            _current_budget.reset(token)


# ---------------------------------------------------------------------------
# STEP 4 (.research/fastapi-grounding-check-token-and-model/step4-corrected-scope.md):
# the two corrected constants, pinned with their derivation (section 12 acceptance items
# 1-3).
# ---------------------------------------------------------------------------


class TestStep4CorrectedConstants:
    def test_grounding_sanity_max_characters_is_600_000(self):
        """step4-corrected-scope.md sections 2-3: 600,000 is the largest judge-content size
        (len(source) + len(serialized candidate)) at which Gate B's real measured judge
        latency satisfies the design's own byte criterion (max <= 0.5 x the 40s large-input
        timeout). 953,500 and 1,581,083 chars were measured and both FAILED it (max 25.66s /
        32.47s); 600,000 PASSED with a 3.2x margin (max 6.32s). The measured 560-encounter
        dev corpus tops out at 317,343 chars -- 1.89x under this cap."""
        assert clinical_grounding.GROUNDING_SANITY_MAX_CHARACTERS == 600_000

    def test_max_judge_input_bytes_default_is_700_000(self):
        """step4-corrected-scope.md section 4: 700,000 = 1.055883 * 600,000 + 3,384
        (636,914 B, the worst-ever-measured escape shape at the corrected cap) plus ~9.96%
        margin, and clears Gate B's real measured body at that cap (637,765 B) by ~9.8%. Was
        never shipped as 2,000,000 -- that round-9 figure was withdrawn before implementation
        once Gate B's real corpus measurement (max 317,343 chars) replaced the 1,581,083-char
        estimate it was sized for."""
        assert WorkBudget().max_judge_input_bytes == 700_000

    def test_max_judge_input_bytes_clears_the_worst_measured_escape_shape_with_margin(
        self,
    ):
        """step4-corrected-scope.md section 12 acceptance item 2 -- the exact test it
        prescribes: pin 700_000 >= 1.055883 * 600_000 + 3_384 (636,914) so a future cap change
        that outgrows the byte margin fails a test rather than producing
        GROUNDING_REQUEST_TOO_LARGE in production."""
        worst_shape_body_at_cap = (
            1.055883 * clinical_grounding.GROUNDING_SANITY_MAX_CHARACTERS + 3_384
        )
        assert worst_shape_body_at_cap == pytest.approx(636_914, abs=1)
        assert WorkBudget().max_judge_input_bytes >= worst_shape_body_at_cap

    def test_large_judge_body_threshold_stays_below_the_ceiling(self):
        """step4-corrected-scope.md section 12 acceptance item 3: _LARGE_JUDGE_BODY_BYTES must
        stay below max_judge_input_bytes, or the large-input timeout band (500,000-700,000 B)
        collapses to empty and Step 4's timeout machinery becomes unreachable by construction
        -- not merely by corpus (round9-revision.md section 8.4.3(a) draws exactly this
        distinction). Also confirms _LARGE_JUDGE_BODY_BYTES itself was NOT lowered, which
        step4-corrected-scope.md section 2 explicitly forbids."""
        assert clinical_grounding._LARGE_JUDGE_BODY_BYTES == 500_000
        assert (
            clinical_grounding._LARGE_JUDGE_BODY_BYTES
            < WorkBudget().max_judge_input_bytes
        )


# ---------------------------------------------------------------------------
# STEP 4: direct evidence that the large-input judge mode is now genuinely reachable end to
# end, not merely correct-if-reached (which this file's module docstring explicitly
# disclaimed for Steps 0-2 -- no call site there could ever build a body over
# _LARGE_JUDGE_BODY_BYTES).
# ---------------------------------------------------------------------------


class TestStep4LargeInputJudgeMode:
    def test_real_body_between_500k_and_700k_bytes_is_admitted_and_takes_the_clamp_path(
        self,
    ):
        # 560,000 plain ASCII chars -> a real ~563,926 B wire body (empirically verified
        # against the shipped sizer): safely under the 600,000-char sanity bound (sanity_len
        # ~= 560,025) yet over the 500,000-byte large-body threshold -- landing it in the
        # exact 500,000-700,000 B band step4-corrected-scope.md section 8 says stays empty on
        # today's real corpus but must be live-if-reached.
        source = "x" * 560_000
        candidate = {"clinical_summary": "y"}
        payload = clinical_grounding._judge_payload(candidate)
        user_message = clinical_grounding._build_judge_message(
            source, payload, "clinical_summary"
        )
        body_bytes = clinical_grounding.judge_request_bytes(user_message)

        # 1. The body really is in the large-input band Step 4 opens up.
        assert clinical_grounding._LARGE_JUDGE_BODY_BYTES < body_bytes <= 700_000

        # 2. It is admitted END TO END by grounding_request_fits under the production-default
        #    WorkBudget (max_judge_input_bytes=700_000) -- not just accepted by the sizer in
        #    isolation.
        budget = WorkBudget(deadline=time.monotonic() + 200)
        token = _current_budget.set(budget)
        try:
            fit = clinical_grounding.grounding_request_fits(source, candidate)
            assert fit.fits, fit.reason
            assert fit.body_bytes == body_bytes
        finally:
            _current_budget.reset(token)

        def timeout_with_remaining(remaining_s):
            budget = WorkBudget(deadline=time.monotonic() + remaining_s)
            token = _current_budget.set(budget)
            try:
                return clinical_grounding._judge_timeout_s(body_bytes)
            finally:
                _current_budget.reset(token)

        # 3. Genuinely takes the CLAMP path, not the constant-30s ordinary path. The ordinary
        #    path (TestJudgeTimeoutScoping.test_12c) returns EXACTLY 30 regardless of the
        #    remaining clock; this body's timeout instead VARIES with the remaining clock,
        #    which is only possible if the early `if body_bytes <= _LARGE_JUDGE_BODY_BYTES:
        #    return _JUDGE_TIMEOUT_S` return was NOT taken for it -- i.e. the clamp arithmetic
        #    below it ran for real, for the first time this body size has ever been able to.
        ample = timeout_with_remaining(200)  # clock not the binding constraint
        assert ample == clinical_grounding._JUDGE_LARGE_TIMEOUT_S == 40
        assert ample != clinical_grounding._JUDGE_TIMEOUT_S  # NOT the ordinary 30s path

        moderate = timeout_with_remaining(50)  # (min(90, ~49) - 10) / 2 ~= 19.5
        assert moderate == pytest.approx(19.5, abs=0.1)
        assert moderate not in (
            clinical_grounding._JUDGE_TIMEOUT_S,
            clinical_grounding._JUDGE_LARGE_TIMEOUT_S,
        )

        with pytest.raises(DocumentProcessingError) as excinfo:
            timeout_with_remaining(15)  # (min(90, ~14) - 10) / 2 ~= 2 < _JUDGE_MIN_LARGE_TIMEOUT_S
        assert excinfo.value.reason_code == "GROUNDING_LATENCY_GATE"


# ---------------------------------------------------------------------------
# Test 11 (round9-revision.md section 11): dispatch multiplier, STEP 4. Direct evidence that
# the x2 reservation is wired ONLY at chain.py's site-2 final audit (_verify_final_with_retry)
# and that sites 1 (_verify_stage's standalone branch), 3 (_audit_once_retried) and 4
# (_verify_final's single whole-candidate audit) all still reserve at the Step 0-2 default of
# dispatches=1.
# ---------------------------------------------------------------------------


class TestStep4DispatchScoping:
    @pytest.mark.asyncio
    async def test_dispatch_count_is_scoped_to_site_2_only(self, monkeypatch):
        assert clinical_grounding._JUDGE_DISPATCHES == 2

        real_reserve = clinical_grounding.reserve_input_bytes
        recorded = []

        def spy_reserve(budget, body_bytes, dispatches):
            recorded.append(dispatches)
            return real_reserve(budget, body_bytes, dispatches)

        monkeypatch.setattr(clinical_grounding, "reserve_input_bytes", spy_reserve)
        run = _passing_run()
        p1, p2, p3 = _settings_patches(run)

        chain_instance = chain.AttachmentSummarizationChain()
        chain_instance._model = object()
        candidate = NS(model_dump=lambda: {"clinical_summary": "irrelevant"})

        with p1, p2, p3:
            # Site 2: chain.py's _verify_final_with_retry (Regime B final audit) -- the ONLY
            # call site that should reserve at dispatches=_JUDGE_DISPATCHES=2.
            token = chain._deferred_grounding.set(None)
            try:
                await chain_instance._verify_final_with_retry("source", candidate)
            finally:
                chain._deferred_grounding.reset(token)
            assert recorded[-1] == clinical_grounding._JUDGE_DISPATCHES == 2

            # Site 1: _verify_stage's standalone branch (audits is None) -- default
            # dispatches=1, unchanged from Step 2.
            token = chain._deferred_grounding.set(None)
            try:
                await chain_instance._verify_stage(
                    "evidence", candidate, stage="synthesis"
                )
            finally:
                chain._deferred_grounding.reset(token)
            assert recorded[-1] == 1

            # Site 3: _audit_once_retried (Regime A staged replay) -- default dispatches=1.
            await chain_instance._audit_once_retried("evidence", candidate)
            assert recorded[-1] == 1

            # Site 4: _verify_final's single whole-candidate audit -- default dispatches=1.
            output_a = NS(source_document_id="doc-a")
            audits = [("synthesis", "evidence-a", output_a)]
            token = chain._deferred_grounding.set(audits)
            try:
                await chain_instance._verify_final(
                    "source", candidate, accepted_ids={"doc-a"}
                )
            finally:
                chain._deferred_grounding.reset(token)
            assert recorded[-1] == 1

        # Exactly one x2 reservation across all four call sites exercised above.
        assert recorded.count(2) == 1
        assert recorded.count(1) == 3

