"""Step 1 (round9-revision.md section 10, prerequisite defined in section 6): REGIME_SPLIT_CHARS
decouples the Regime A/B audit-topology split from the grounding size gate. Pure refactor --
these tests pin the constant's value and confirm `analyze()`'s regime-split decision still
evaluates identically to the pre-change `source_size <= 80_000` expression, including at its
boundary.

Step 2 (round9-revision.md section 4.4(c)): the grounding size gate's own constant
(GROUNDING_MAX_CHARACTERS) is deleted -- there is no longer anything to re-derive
REGIME_SPLIT_CHARS FROM even by coincidence. Section 11 test 5 requires confirming that no
module-level name in chain.py other than REGIME_SPLIT_CHARS participates in the regime
decision; the grep-style assertion below pins that directly against chain.py's own source
rather than against a same-valued sibling constant that no longer exists.
"""
import inspect

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import DocumentAttachment


def test_regime_split_chars_is_pinned_at_80_000():
    assert chain.REGIME_SPLIT_CHARS == 80_000


def test_regime_decision_references_no_other_grounding_constant():
    """section 11 test 5: since the grounding size gate's own constant no longer exists after
    Step 2, the only name `analyze()`'s regime-split decision can reference is
    REGIME_SPLIT_CHARS itself."""
    source = inspect.getsource(chain.AttachmentSummarizationChain.analyze)
    decision_line = next(line for line in source.splitlines() if "_deferred_grounding.set(" in line)
    assert "REGIME_SPLIT_CHARS" in decision_line
    for name in ("GROUNDING_MAX_CHARACTERS", "GROUNDING_SANITY_MAX_CHARACTERS", "_LARGE_JUDGE_RETRY_CUTOFF_BYTES"):
        assert name not in decision_line


def _document(size: int) -> DocumentAttachment:
    return DocumentAttachment(
        file_path="s3://bucket/doc.pdf",
        content_type="application/pdf",
        extracted_text="x" * size,
        extraction_error=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_size, expect_regime_a",
    [
        (79_999, True),  # below the split -> Regime A (deferred list, [])
        (80_000, True),  # at the split, inclusive -> Regime A
        (80_001, False),  # above the split -> Regime B (None)
    ],
)
async def test_analyze_regime_split_boundary_unchanged(monkeypatch, source_size, expect_regime_a):
    """`analyze()` sets the `_deferred_grounding` contextvar before delegating to `_analyze`;
    stub `_analyze` to capture that value instead of doing real extraction/synthesis work.
    """
    observed = {}

    async def fake_analyze(self, appointment_context, documents, *, encounter_id=None):
        observed["deferred"] = chain._deferred_grounding.get()

    monkeypatch.setattr(chain.AttachmentSummarizationChain, "_analyze", fake_analyze)

    instance = chain.AttachmentSummarizationChain()
    await instance.analyze({}, [_document(source_size)])

    assert (observed["deferred"] == []) is expect_regime_a
    assert (observed["deferred"] is None) is not expect_regime_a
