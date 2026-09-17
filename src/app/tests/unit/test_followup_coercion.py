"""PR-11 (root cause 2): AttachmentSummarizationResponse.follow_up must coerce the model's
occasional dict-shaped entries instead of failing pydantic validation.

The synthesis stage declares follow_up: list[str], but the model occasionally echoes each
source document's own FollowUpDetail shape (`{"follow_up": ..., "source_quote": ...}` -- see
`validated_source_records` in the synthesis prompt, built from DocumentSummary.follow_up:
list[FollowUpDetail]) instead of a flat string. Confirmed from real pydantic_ai
ValidationErrors captured during the acceptance-test re-run:
    follow_up.0
      Input should be a valid string [type=string_type,
      input_value={'follow_up': 'You were t...rce_quote': 'Follow-up'}, input_type=dict]
With _SYNTHESIS_RETRIES = 1, exhausting both the internal pydantic_ai retry and the outer
`_synthesize_records` repair attempt fails the entire appointment. This coerces the one
confirmed shape at the pydantic boundary so the mismatch never reaches validation at all.
"""

from src.app.models.attachment_summarization import AttachmentSummarizationResponse


def _response(follow_up):
    return AttachmentSummarizationResponse(
        clinical_summary="Test summary.",
        documents_analyzed=1,
        follow_up=follow_up,
    )


def test_follow_up_dict_shape_is_coerced_to_plain_string():
    """The exact dict shape observed in production ValidationErrors -- a
    FollowUpDetail-shaped dict instead of a plain string -- is normalized to its
    `follow_up` text instead of raising a validation error."""
    response = _response(
        [{"follow_up": "You were told to follow up with cardiology in 2 weeks",
          "source_quote": "Follow-up with cardiology in 2 weeks."}]
    )
    assert response.follow_up == ["You were told to follow up with cardiology in 2 weeks"]


def test_follow_up_plain_strings_pass_through_unchanged():
    response = _response(["You were told to return in 6 weeks", "Repeat labs in 3 months"])
    assert response.follow_up == ["You were told to return in 6 weeks", "Repeat labs in 3 months"]


def test_follow_up_mixed_strings_and_dicts_are_each_coerced():
    response = _response(
        [
            "You were told to return in 6 weeks",
            {"follow_up": "Repeat labs in 3 months", "source_quote": "repeat labs in 3 months"},
        ]
    )
    assert response.follow_up == ["You were told to return in 6 weeks", "Repeat labs in 3 months"]


def test_follow_up_unrecognized_dict_shape_still_fails_validation():
    """An unrecognized dict shape (no `follow_up` string key) is NOT silently accepted --
    it still fails pydantic validation, same as before this fix. The coercion only handles
    the one confirmed shape; it must not become a blanket list[Any] escape hatch."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _response([{"text": "Some other shape entirely"}])
