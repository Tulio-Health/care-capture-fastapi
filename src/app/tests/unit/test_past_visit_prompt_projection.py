"""T-AI-14b (r9-n-01): summary ``metadata`` never reaches the chatbot prompt.

The Node API chatbot cache copies each summary's ``metadata`` (selection
telemetry, document eligibility, fingerprints, ...) next to the clinical
fields.  The past-visit intent must project matched summaries to an explicit
field list before serializing them into the response prompt, on both the
follow-up path and the new-question path.  No model / network / Redis calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.app.chains.ai_chat_intents.past_visit_intent import chain as pv_chain
from src.app.chains.ai_chat_intents.past_visit_intent.chain import (
    _PROMPT_FIELDS,
    PastVisitIntentChain,
)
from src.app.models.past_visit_query import PastVisitQuery

SENTINELS = (
    "metadata",
    "summaryMetadata",
    "visit_summary_selection",
    "not_allowlisted_types",
    "not_allowlisted_documents",
    "allowlist_version",
    "document_eligibility",
    "SENTINEL-LABEL-Zq9x",
    "SENTINEL-ELIG-Zq9x",
)


def _summary(sid: str, **overrides):
    row = {
        "id": sid,
        "appointmentId": f"appt-{sid}",
        "summaryText": f"Rotator cuff follow-up text {sid}",
        "keyPoints": ["KP-" + sid],
        "medications": ["Ibuprofen"],
        "diagnoses": ["Shoulder pain"],
        "instructions": ["Ice twice daily"],
        "recommendations": ["Physical therapy"],
        "appointmentDate": "2025-01-17",
        "providerName": "Surena Namdari",
        "providerSpecialty": "Orthopedic Surgery",
        "appointmentPurpose": "follow-up",
        "hasSummary": True,
        "metadata": {
            "visit_summary_selection": {
                "not_allowlisted_types": {"SENTINEL-LABEL-Zq9x": 3},
                "allowlist_version": "v2",
            },
            "document_eligibility": {"marker": "SENTINEL-ELIG-Zq9x"},
        },
        "summaryMetadata": {"marker": "SENTINEL-ELIG-Zq9x"},
    }
    row.update(overrides)
    return row


class _FakeResponseChain:
    def __init__(self):
        self.inputs = []

    async def ainvoke(self, payload, config=None):
        self.inputs.append(payload)
        return "ok"


class _FakeQueryChain:
    def invoke(self, payload, config=None):
        return PastVisitQuery()


@pytest.fixture
def chain():
    with patch.object(
        pv_chain, "redis_client", MagicMock(get=MagicMock(return_value=None))
    ):
        c = PastVisitIntentChain(db=None)
        c._response_content_chain = _FakeResponseChain()
        c._query_chain = _FakeQueryChain()
        yield c


def _rendered_prompt(chain, payload) -> str:
    """The real response prompt, as the LLM would receive it."""
    messages = chain.response_prompt.format_messages(**payload)
    return "\n".join(m.content for m in messages)


def _assert_clean(chain, summaries_in):
    (payload,) = chain._response_content_chain.inputs
    serialized = payload["matched_summaries"]
    rendered = _rendered_prompt(chain, payload)
    for text in (serialized, rendered):
        for sentinel in SENTINELS:
            assert sentinel not in text, sentinel
    # Retained fields still appear, with their values.
    parsed = json.loads(serialized)
    assert [p["id"] for p in parsed] == [s["id"] for s in summaries_in]
    for p, s in zip(parsed, summaries_in):
        assert set(p) == set(_PROMPT_FIELDS)
        for k in _PROMPT_FIELDS:
            assert p[k] == s[k]
    assert "Rotator cuff follow-up text" in rendered
    assert "Surena Namdari" in rendered
    # Inputs are not mutated (filtering / conversation context still see them).
    assert all("metadata" in s for s in summaries_in)


async def test_new_question_path_prompt_has_no_metadata(chain):
    summaries = [_summary("s1"), _summary("s2", appointmentDate="2025-02-01")]
    result = await chain.handle_intent(
        text="what did the orthopedist say?",
        context={"enriched_summaries": summaries},
        conversation_id="c1",
    )
    assert result.responses[0].content == "ok"
    _assert_clean(
        chain, sorted(summaries, key=lambda s: s["appointmentDate"], reverse=True)
    )


async def test_followup_path_prompt_has_no_metadata(chain):
    summaries = [_summary("s1"), _summary("s2", providerName="Other Doc")]
    context = {
        "enriched_summaries": summaries,
        "conversation_context": {
            "lastProvider": "Surena Namdari",
            "lastMatchedSummaryIds": ["s1"],
        },
    }
    result = await chain.handle_intent(
        text="what was the medication?", context=context, conversation_id="c1"
    )
    assert result.responses[0].content == "ok"
    _assert_clean(chain, [summaries[0]])


async def test_summary_without_summary_row_keeps_has_summary_false(chain):
    # Appointment with no summary: the cache row has null text and metadata.
    row = _summary(
        "x",
        id=None,
        summaryText=None,
        hasSummary=False,
        metadata=None,
        summaryMetadata=None,
    )
    await chain.handle_intent(
        text="show my visits",
        context={"enriched_summaries": [row]},
        conversation_id="c1",
    )
    (payload,) = chain._response_content_chain.inputs
    parsed = json.loads(payload["matched_summaries"])
    assert parsed[0]["hasSummary"] is False
    assert "metadata" not in parsed[0]


def test_prompt_view_is_explicit_allowlist_and_drops_unknown_keys():
    row = _summary("s1", futureKey="should not leak")
    (view,) = pv_chain._prompt_view([row])
    assert set(view) == set(_PROMPT_FIELDS)
    assert "futureKey" not in view and "metadata" not in view
    assert "metadata" in row  # input untouched
