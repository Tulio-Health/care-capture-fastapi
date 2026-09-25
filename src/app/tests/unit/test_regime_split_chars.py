"""Step 1 (round9-revision.md section 10, prerequisite defined in section 6): REGIME_SPLIT_CHARS
decouples the Regime A/B audit-topology split from GROUNDING_MAX_CHARACTERS. Pure refactor --
these tests pin the constant's value and confirm `analyze()`'s regime-split decision still
evaluates identically to the pre-change `source_size <= GROUNDING_MAX_CHARACTERS // 2`
expression, including at its boundary.
"""
import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.clinical_grounding import GROUNDING_MAX_CHARACTERS


def test_regime_split_chars_is_pinned_at_80_000():
    assert chain.REGIME_SPLIT_CHARS == 80_000
    # Same value as today's GROUNDING_MAX_CHARACTERS // 2, but not re-derived from it --
    # a later change to GROUNDING_MAX_CHARACTERS must not move this constant.
    assert chain.REGIME_SPLIT_CHARS == GROUNDING_MAX_CHARACTERS // 2


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
