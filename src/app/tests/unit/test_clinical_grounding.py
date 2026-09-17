"""PR-11 (root cause 1): validate_high_risk_claims must tolerate a genuine paraphrase of
real source content while still failing closed on a claim with zero source support.

Before this fix, `validate_high_risk_claims` matched candidate high-risk wording against
source clauses with a verbatim `candidate in evidence` substring check. The extraction agent
is explicitly instructed to paraphrase clinical content into patient-facing prose, so almost
any real, correctly-grounded claim failed this check purely because the wording did not
appear character-for-character in the source -- and the entire batch was rejected, not just
the offending clause. The fix reuses procedure_extraction.chain._quote_supported's existing
fuzzy-match discipline (threshold=0.85, the same one already trusted for follow_up/quote
grounding elsewhere in this codebase) instead of inventing a new algorithm or threshold.
"""

import pytest

from src.app.services.clinical_grounding import validate_high_risk_claims
from src.app.services.document_extraction import DocumentProcessingError


def _normalize(value: str) -> str:
    """Mirrors validate_high_risk_claims' internal `normalize` lambda, used only to prove
    the old verbatim check would have rejected test 1's candidate (the before/after proof)."""
    return " ".join(value.casefold().split()).strip(" .")


def test_paraphrased_high_risk_claim_now_passes():
    """A real, correctly-grounded medication claim, paraphrased (not verbatim) from its
    source clause, must be accepted. This is the actual bug fix.

    Before/after proof: the candidate is deliberately NOT a verbatim substring of the
    (normalized) source -- it adds a natural trailing word ("today") the source doesn't have
    at that position -- so the OLD `candidate in evidence` check would have rejected it and
    failed the whole batch, even though the claim is fully, faithfully grounded.
    """
    source = (
        "Active Medications: Aspirin 81 mg oral tablet, newly started for cardiovascular "
        "risk reduction, per today's clinic note."
    )
    candidate = {
        "medications_mentioned": [
            "Aspirin 81 mg oral tablet, newly started for cardiovascular risk reduction today"
        ]
    }

    # Prove the old verbatim check would have failed this exact case.
    assert _normalize(candidate["medications_mentioned"][0]) not in _normalize(source)

    # New fuzzy check accepts it -- no exception raised.
    validate_high_risk_claims(source, candidate)


def test_fabricated_high_risk_claim_still_fails_closed():
    """Load-bearing negative control: a candidate with ZERO support anywhere in the source
    (a genuine hallucination, phrased however) must still raise GROUNDING_VALIDATION_FAILED
    (canonicalized to CLINICAL_EVIDENCE_FAILED). This proves the fuzzy-match fix did not
    turn the check into an unconditional pass -- 0.85 similarity tolerates paraphrase of real
    content, not fabrication of content that was never there.
    """
    source = "Patient denies any medication use. No active prescriptions on file."
    candidate = {
        "medications_mentioned": [
            "You were newly started on Warfarin 5mg daily for atrial fibrillation"
        ]
    }

    with pytest.raises(DocumentProcessingError) as excinfo:
        validate_high_risk_claims(source, candidate)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"
    assert excinfo.value.reason_code == "GROUNDING_VALIDATION_FAILED"


def test_borderline_similarity_below_threshold_still_fails():
    """A candidate that shares real wording with the source but drifts too far from it
    (below the 0.85 longest-contiguous-match ratio) must still fail closed. This shows the
    threshold is discriminating, not a coincidental pass on every input that shares any words
    with the source at all.
    """
    source = (
        "Active Medications: Aspirin 81 mg oral tablet, newly started for cardiovascular "
        "risk reduction, per today's clinic note."
    )
    # Same clinical fact, but padded with enough added patient-facing framing that the
    # longest unbroken match against the source clause drops below 0.85 of the candidate's
    # length -- this is genuinely too loose a paraphrase for this deliberately conservative
    # check to accept.
    candidate = {
        "medications_mentioned": [
            "Aspirin 81 mg oral tablet, newly started for cardiovascular risk reduction "
            "to help protect your heart"
        ]
    }

    with pytest.raises(DocumentProcessingError) as excinfo:
        validate_high_risk_claims(source, candidate)

    assert excinfo.value.code == "CLINICAL_EVIDENCE_FAILED"

