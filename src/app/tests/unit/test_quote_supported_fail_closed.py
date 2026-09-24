"""Round-3 revision of audit R9 (round-2 red-team MAJOR-3): the LIVE _quote_supported
verdict must be exactly origin/develop's scoring; the windowed similarity exists only as a
logged side-channel. The rejects below are red-team round 2's adversarial near-misses -- the
classes GROUNDING_POLICY names first (dose, dates, negation, ordered-vs-performed) -- which
the live score fail-closes on and the windowed metric was measured to accept.
"""
import difflib
import random

from src.app.chains.procedure_extraction.chain import _normalize, _quote_supported

SOURCE = (
    "PROCEDURE NOTE\n"
    "Patient underwent transesophageal echocardiogram on 2026-07-06. There is no evidence of "
    "intracardiac thrombus. Ejection fraction is 55 percent. Mild mitral regurgitation noted.\n"
    "Medications on discharge: aspirin 81 mg by mouth daily, atorvastatin 20 mg nightly, "
    "metoprolol 12.5 mg twice daily.\n"
    "Plan: return in 6 weeks for follow-up labs. Aortic valve replacement was recommended but "
    "not performed during this admission.\n"
) * 6


def _develop_reference(quote, source, threshold=0.85):
    """Literal reimplementation of origin/develop's _quote_supported -- the pinned live verdict."""
    q, src = _normalize(quote), _normalize(source)
    if not q:
        return False
    if q in src:
        return True
    matcher = difflib.SequenceMatcher(None, q, src)
    match = matcher.find_longest_match(0, len(q), 0, len(src))
    return match.size / max(len(q), 1) >= threshold


ADVERSARIAL_REJECTS = [
    ("dose 81 -> 810 mg (10x)", "aspirin 810 mg by mouth daily, atorvastatin 20 mg nightly"),
    ("dose 20 -> 200 mg", "atorvastatin 200 mg nightly, metoprolol 12.5 mg twice daily"),
    ("EF 55 -> 35 percent", "Ejection fraction is 35 percent. Mild mitral regurgitation noted."),
    ("date shifted 2 months", "transesophageal echocardiogram on 2026-09-06. There is no evidence of intracardiac"),
    ("ordered -> performed", "Aortic valve replacement was recommended and performed during this admission."),
    ("follow-up 6 -> 16 weeks", "Plan: return in 16 weeks for follow-up labs. Aortic valve replacement was recommended"),
    ("fully fabricated", "Coronary artery bypass grafting times three was performed without complication."),
]


def test_adversarial_near_misses_fail_closed():
    for name, quote in ADVERSARIAL_REJECTS:
        assert _quote_supported(quote, SOURCE) is False, name


def test_negation_dropped_matches_develop_not_a_new_hole():
    """Red-team round 2 measured develop's own metric ALREADY accepting this negation-dropped
    near-miss (True -> True: "the old metric was not safe either"). It is pinned here as
    develop-parity -- NOT as a reject -- so any future change that silently flips it in
    either direction surfaces as an explicit decision instead of an accident."""
    quote = "There is evidence of intracardiac thrombus. Ejection fraction is 55 percent."
    assert _quote_supported(quote, SOURCE) is _develop_reference(quote, SOURCE) is True


def test_verbatim_and_whitespace_noise_accepted():
    assert _quote_supported("aspirin 81 mg by mouth daily", SOURCE) is True
    assert _quote_supported("Aspirin  81 mg\n by mouth   DAILY", SOURCE) is True


def test_live_verdict_identical_to_develop_reference():
    """Differential pin: any semantic drift of the live verdict from origin/develop's scoring
    fails here, including a re-substitution of the windowed side-channel metric."""
    cases = [q for _, q in ADVERSARIAL_REJECTS]
    cases += ["aspirin 81 mg by mouth daily", "", "   ", "zzz entirely unrelated text zzz"]
    rng = random.Random(20260924)
    base = _normalize(SOURCE)
    for _ in range(300):
        qlen = rng.choice([25, 45, 80, 140])
        start = rng.randrange(0, len(base) - qlen)
        q = base[start:start + qlen]
        i = rng.randrange(1, qlen - 1)
        cases.append(q[:i] + "X" + q[i + 1:])  # interior substitution
        cases.append(q[:i] + q[i + 1:])        # interior deletion
    for q in cases:
        assert _quote_supported(q, SOURCE) == _develop_reference(q, SOURCE), q[:60]
