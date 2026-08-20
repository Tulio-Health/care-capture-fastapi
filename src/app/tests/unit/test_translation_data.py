"""Unit tests for Task 4 (translation plumbing for the new `data` jsonb column):
`_same_structure`'s structural-corruption guard and `TranslationChain.translate_conversation_summary`'s
`data` merge/fallback behavior. Fully mocked - no real LLM calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.app.chains.translation.chain import TranslationChain, _same_structure
from src.app.models.translation import TranslatedSummary


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
async def test_translate_conversation_summary_merges_valid_translated_data():
    chain = _chain_with_mocked_agent({"reason": "es reason", "outcome": "es outcome"})
    summary_data = {
        "summary_text": "text",
        "data": {"reason": "en reason", "outcome": "en outcome"},
    }

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["data"] == {"reason": "es reason", "outcome": "es outcome"}


@pytest.mark.asyncio
async def test_translate_conversation_summary_falls_back_on_corrupted_data():
    chain = _chain_with_mocked_agent(
        {"reason": "es reason"}
    )  # dropped the "outcome" key
    original_data = {"reason": "en reason", "outcome": "en outcome"}
    summary_data = {"summary_text": "text", "data": original_data}

    result = await chain.translate_conversation_summary(summary_data, "es")

    assert result["data"] == original_data
