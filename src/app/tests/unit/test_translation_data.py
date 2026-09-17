"""Unit tests for Task 4 (translation plumbing for the new `data` jsonb column):
`_same_structure`'s structural-corruption guard and `TranslationChain.translate_conversation_summary`'s
`data` merge/fallback behavior. Fully mocked - no real LLM calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.app.chains.translation.chain import TranslationChain, _same_structure
from src.app.models.translation import TranslatedSummary


@pytest.fixture(autouse=True)
def mock_verify_grounding(monkeypatch):
    """`translate_conversation_summary` does `from src.app.services.clinical_grounding import
    verify_grounding` INSIDE its own function body (chain.py:252), not at module level - a
    fresh attribute lookup on `clinical_grounding` every call, so patching it here at its
    DEFINITION site is what actually intercepts it. Patching `chain.verify_grounding` instead
    would be a silent no-op, since chain.py never binds that name at module scope to patch.

    `get_pydantic_ai_model` is the opposite case: chain.py imports it at MODULE level (top of
    file), so `self.model`'s lazy construction resolves the name already bound in chain.py's
    own namespace - patching the definition site (llm_factory.get_pydantic_ai_model) would be
    the no-op here, and without a patch at all `self.model` raises "OpenAI API key not
    configured" before verify_grounding is ever reached in this credential-less test env,
    since Python evaluates `verify_grounding`'s arguments (including `self.model`) before the
    (mocked) call happens.
    """
    stub = AsyncMock(return_value=None)
    monkeypatch.setattr("src.app.services.clinical_grounding.verify_grounding", stub)
    monkeypatch.setattr(
        "src.app.chains.translation.chain.get_pydantic_ai_model",
        lambda *a, **k: MagicMock(),
    )
    return stub


def test_same_structure_matching_flat_dict():
    original = {"reason": "en reason", "outcome": "en outcome"}
    translated = {"reason": "es reason", "outcome": "es outcome"}
    assert _same_structure(original, translated)


def test_same_structure_detects_dropped_key():
    original = {"reason": "en reason", "outcome": "en outcome"}
    translated = {"reason": "es reason"}
    assert not _same_structure(original, translated)


def test_same_structure_detects_renamed_key():
    original = {"reason": "en reason"}
    translated = {"reasons": "es reason"}
    assert not _same_structure(original, translated)


def test_same_structure_recurses_into_nested_values():
    original = {"outer": {"inner": "en"}}
    translated_ok = {"outer": {"inner": "es"}}
    translated_bad = {"outer": {"different_key": "es"}}
    assert _same_structure(original, translated_ok)
    assert not _same_structure(original, translated_bad)


def _chain_with_mocked_agent(translated_data) -> TranslationChain:
    chain = TranslationChain()
    mock_agent = SimpleNamespace()
    mock_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            output=TranslatedSummary(
                summary_text="translated text",
                key_points=None,
                medications=None,
                diagnoses=None,
                instructions=None,
                recommendations=None,
                data=translated_data,
            )
        )
    )
    chain._agent = mock_agent
    return chain


@pytest.mark.asyncio
async def test_translate_conversation_summary_merges_valid_translated_data(
    mock_verify_grounding,
):
    chain = _chain_with_mocked_agent({"reason": "es reason", "outcome": "es outcome"})
    summary_data = {
        "summary_text": "text",
        "data": {"reason": "en reason", "outcome": "en outcome"},
    }

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["data"] == {"reason": "es reason", "outcome": "es outcome"}
    # A future refactor that accidentally drops the grounding-verification pass must fail
    # loudly here, not silently ship untranslated-meaning-checked content.
    mock_verify_grounding.assert_awaited_once()


@pytest.mark.asyncio
async def test_translate_conversation_summary_falls_back_only_on_the_corrupted_key(
    mock_verify_grounding,
):
    """PR-3a: the whole-blob revert was replaced by a per-key one (see
    test_translation_data_guard.py for the fuller coverage) -- a key the model dropped
    reverts to its original value, but a sibling key that translated fine is NOT dragged
    back to English with it."""
    chain = _chain_with_mocked_agent(
        {"reason": "es reason"}
    )  # dropped the "outcome" key
    original_data = {"reason": "en reason", "outcome": "en outcome"}
    summary_data = {"summary_text": "text", "data": original_data}

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["data"] == {"reason": "es reason", "outcome": "en outcome"}
    mock_verify_grounding.assert_awaited_once()


def _chain_with_mocked_agent_recommendations(
    translated_recommendations: list[dict] | None,
) -> TranslationChain:
    chain = TranslationChain()
    mock_agent = SimpleNamespace()
    mock_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            output=TranslatedSummary(
                summary_text="translated text",
                key_points=None,
                medications=None,
                diagnoses=None,
                instructions=None,
                recommendations=translated_recommendations,
                data=None,
            )
        )
    )
    chain._agent = mock_agent  # type: ignore[assignment]
    return chain


@pytest.mark.asyncio
async def test_translate_conversation_summary_falls_back_on_renamed_recommendations_key(
    mock_verify_grounding,
) -> None:
    original = [{"recommendation": "en recommendation"}]
    chain = _chain_with_mocked_agent_recommendations(
        [{"advice": "es recommendation"}]
    )  # renamed key
    summary_data = {"summary_text": "text", "recommendations": original}

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["recommendations"] == original
    mock_verify_grounding.assert_awaited_once()


@pytest.mark.asyncio
async def test_translate_conversation_summary_falls_back_when_recommendations_nulled_out(
    mock_verify_grounding,
) -> None:
    original = [{"recommendation": "en recommendation"}]
    chain = _chain_with_mocked_agent_recommendations(
        None
    )  # invented None from a non-None original
    summary_data = {"summary_text": "text", "recommendations": original}

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["recommendations"] == original
    mock_verify_grounding.assert_awaited_once()
