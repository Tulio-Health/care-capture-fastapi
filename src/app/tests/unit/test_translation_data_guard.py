"""Guards PR-3a's translation `data`-field fix: the whole-blob revert
(`TranslationChain._GUARDED_FIELDS` loop) was replaced by `_guard_translated_data`, which
reverts only the sub-keys whose structure fails to survive translation instead of dragging
every sibling key back to English with it. See §7 Check 7 (a)-(d) in
care-capture-nodeapi/.claude/debug-reports/2026-09-08-summary-fix-plan/revision-round3.md.

Tests `_guard_translated_data` directly (pure function, no LLM/DB mocking needed).
"""

from src.app.chains.translation.chain import _guard_translated_data


def test_non_dict_translated_reverts_the_whole_field():
    """(a) precondition (i): translated.data is not a dict (None, or a degraded list) ->
    revert the whole field, since there is nothing to index per-key."""
    original = {"procedures_mentioned": ["a"], "follow_up": ["b"]}

    assert _guard_translated_data(original, None) == original
    assert _guard_translated_data(original, ["not", "a", "dict"]) == original


def test_key_missing_from_translated_reverts_only_that_key():
    """(b) precondition (ii): a key present in original but absent from translated is treated
    as corrupted-for-that-key via the _MISSING sentinel, never a raw KeyError."""
    original = {"procedures_mentioned": ["a"], "follow_up": ["b"]}
    translated = {"procedures_mentioned": ["a-es"]}  # follow_up dropped entirely

    result = _guard_translated_data(original, translated)

    assert result == {"procedures_mentioned": ["a-es"], "follow_up": ["b"]}


def test_one_corrupted_key_does_not_drag_down_a_sibling_correctly_translated_key():
    """(c) the core fix: a structurally-corrupted sub-key (length mismatch) reverts on its
    own, while a sibling key that translated fine is NOT reverted alongside it."""
    original = {
        "procedures_mentioned": ["shoulder injection"],
        "follow_up": ["return in 6 weeks", "repeat labs in 3 months"],
    }
    translated = {
        "procedures_mentioned": ["inyección en el hombro"],  # fine, same length (1)
        "follow_up": ["regrese en 6 semanas"],  # corrupted, model dropped one item
    }

    result = _guard_translated_data(original, translated)

    assert result["procedures_mentioned"] == ["inyección en el hombro"]
    assert result["follow_up"] == original["follow_up"]


def test_fully_valid_translation_keeps_every_key_translated():
    """(d) sanity: when every key survives structurally, nothing is reverted."""
    original = {"a": ["x"], "b": {"c": "y"}}
    translated = {"a": ["x-es"], "b": {"c": "y-es"}}

    assert _guard_translated_data(original, translated) == translated


def test_original_none_and_translated_none_is_a_no_op():
    assert _guard_translated_data(None, None) is None


def test_original_none_but_translated_has_data_reverts_to_none():
    """Matches the pre-PR-3a whole-field semantics for this edge case: the model should not
    have invented a `data` object when there wasn't one to translate."""
    assert _guard_translated_data(None, {"a": 1}) is None
