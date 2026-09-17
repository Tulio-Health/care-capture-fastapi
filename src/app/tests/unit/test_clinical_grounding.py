"""PR-12b: validate_high_risk_claims and validate_explicit_facts were deleted entirely.

Both were "what kind of claim is this" classifiers on free-form clinical prose (regex
triggers for initiation/prescribing, visit purpose, and lab interpretation, plus anti-omission
Assessment:/lab-value regexes). PR-12 research (topics B and C) confirmed a real false positive
(a patient's age misread as a lab value purely because "normal" co-occurred with a bare digit)
and confirmed every call site of these functions is followed, unconditionally, by an actual LLM
judge review of the same content -- either immediately inside verify_grounding, or via the
retried final-grounding check added to AttachmentSummarizationChain._analyze for the one call
site that previously had no judge review at all in Regime B (see
test_pr12b_validation_consolidation.py for that call site's own tests).

These tests prove: (1) the exact reproduced false positive no longer blocks the pipeline and
the judge is actually invoked on that content, and (2) a genuine fabrication is still caught --
now solely by the judge. Also covers validate_quotes' switch to fuzzy matching (item 3).
"""

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from src.app.services.clinical_grounding import GroundingVerdict, validate_quotes, verify_grounding
from src.app.services.document_extraction import DocumentProcessingError


def _mock_judge(supported: bool, issues=None):
    return AsyncMock(return_value=NS(output=GroundingVerdict(supported=supported, issues=issues or [])))


@pytest.mark.asyncio
async def test_age_misread_as_lab_value_no_longer_blocks_and_the_judge_still_runs():
    """PR-12 research topic B's exact reproduced false positive: 'Patient is a 20-year-old
    female in normal appearance, not in acute distress.' used to be classified as an
    unsupported LAB INTERPRETATION purely because 'normal' co-occurred with the patient's age
    (a bare digit) -- no lab, no value, no unit. validate_high_risk_claims no longer exists, so
    this must reach (and pass) the real LLM judge instead of being rejected before the judge is
    ever called.
    """
    source = (
        "Lauren M Strimel is a 20 y.o. female presenting today for: Establish Care\n"
        "GENERAL:\nGeneral: Not in acute distress.\nAppearance: Normal appearance."
    )
    candidate = {
        "clinical_findings": [
            "Patient is a 20-year-old female in normal appearance, not in acute distress."
        ]
    }
    run = _mock_judge(supported=True)
    with patch("src.app.core.settings.get_settings", return_value=NS(DOCUMENT_VERIFICATION_MODEL="mock")), \
         patch("src.app.common.llm_factory.get_pydantic_ai_model", return_value=object()), \
         patch("pydantic_ai.Agent", return_value=NS(run=run)):
        await verify_grounding(None, source, candidate)  # must not raise
    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_fabricated_claim_still_caught_solely_by_the_judge():
    """Negative control: a genuine fabrication (medications never documented in source) must
    still fail closed. With the classifier deleted, this protection now comes entirely from
    the LLM judge's verdict."""
    source = "Patient denies any medication use. No active prescriptions on file."
    candidate = {
        "medications_mentioned": [
            "You were newly started on Warfarin 5mg daily for atrial fibrillation"
        ]
    }
    run = _mock_judge(
        supported=False,
        issues=["medications_mentioned lists warfarin which is not documented in the source"],
    )
    with patch("src.app.core.settings.get_settings", return_value=NS(DOCUMENT_VERIFICATION_MODEL="mock")), \
         patch("src.app.common.llm_factory.get_pydantic_ai_model", return_value=object()), \
         patch("pydantic_ai.Agent", return_value=NS(run=run)):
        with pytest.raises(DocumentProcessingError) as excinfo:
            await verify_grounding(None, source, candidate)
    run.assert_awaited_once()
    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"
    assert excinfo.value.reason_code == "GROUNDING_VALIDATION_FAILED"


def test_validate_high_risk_claims_and_validate_explicit_facts_are_removed():
    """PR-12b: both classifier functions are deleted entirely, not merely disabled."""
    import src.app.services.clinical_grounding as clinical_grounding

    assert not hasattr(clinical_grounding, "validate_high_risk_claims")
    assert not hasattr(clinical_grounding, "validate_explicit_facts")


def test_validate_quotes_now_tolerates_a_fuzzy_paraphrase():
    """PR-12b item 3: validate_quotes switched from verbatim `in` to fuzzy _quote_supported
    matching (same primitive/threshold validate_high_risk_claims used to use, and that
    _check_follow_up_grounding already uses)."""
    source = "Blood Pressure: 124/73 mmHg, taken 04/11/2024 10:31 AM CDT."
    # Not a verbatim substring (extra trailing word), but a close fuzzy match.
    validate_quotes(["Blood Pressure: 124/73 mmHg, taken 04/11/2024"], source)


def test_validate_quotes_still_fails_closed_on_zero_support():
    """Negative control: fuzzy matching loosens the comparison, not the fail-closed policy."""
    source = "Blood Pressure: 124/73 mmHg."
    with pytest.raises(DocumentProcessingError) as excinfo:
        validate_quotes(["Patient was started on lisinopril 10mg daily"], source)
    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"
    assert excinfo.value.reason_code == "INVALID_SOURCE_EVIDENCE"
