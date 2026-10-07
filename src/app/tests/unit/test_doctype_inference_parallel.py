"""S0 speed fix: parallel (1-item, bounded fan-out) document-type inference. Offline, models mocked.

Deliberately does NOT use the session `test_client` fixture (it starts the whole app lifespan:
SSM / DB / Redis probes). A minimal FastAPI app that mounts only the inference router is used for
the route tests; Redis is replaced with an in-memory fake.
"""

import asyncio
import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.app.chains.document_type_inference import chain as chain_module
from src.app.chains.document_type_inference.chain import DocumentTypeInferenceChain
from src.app.config.configuration_summary import (
    log_doctype_inference_parallel_configuration,
)
from src.app.config.ssm_loader import SSMParameterLoader
from src.app.core import get_settings
from src.app.core.settings import Settings
from src.app.models.document_type_inference import (
    DocumentTypeInferenceRequest,
    DocumentTypeInferenceResponse,
)
from src.app.routes import document_type_inference as route_module
from src.app.services.bounded_fanout import UNRESOLVED, fan_out
from src.app.services.document_extraction import DocumentProcessingError

ROUTE_PATH = "/care-capture/document-type-inference"

# sha256 of _SYSTEM_PROMPT at the parent commit (b41bc2b): the prompt must not change in S0.
PARENT_PROMPT_SHA256 = (
    "0c6ee60f535124c590104aa18d6680efd6df7425667c585258578a48ed3902ba"
)


# ---------------------------------------------------------------------------
# fan_out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 4, 8])
async def test_fan_out_enforces_concurrency_limit_exactly(limit):
    in_flight = 0
    max_in_flight = 0

    async def worker(item):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return item * 2

    out = await fan_out(list(range(20)), worker, concurrency=limit, deadline_s=10)

    assert max_in_flight == limit  # reached, and never above
    assert out == [i * 2 for i in range(20)]


async def test_fan_out_preserves_input_order_when_completion_order_is_reversed():
    n = 6

    async def worker(item):
        await asyncio.sleep((n - item) * 0.02)  # first item finishes last
        return f"r{item}"

    out = await fan_out(list(range(n)), worker, concurrency=n, deadline_s=10)

    assert out == [f"r{i}" for i in range(n)]


async def test_fan_out_isolates_a_failing_item_into_its_own_slot():
    async def worker(item):
        if item == 2:
            raise RuntimeError("boom")
        return item

    out = await fan_out([0, 1, 2, 3], worker, concurrency=2, deadline_s=10)

    assert out[0] == 0 and out[1] == 1 and out[3] == 3
    assert out[2] is UNRESOLVED
    assert len(out) == 4  # never omitted


async def test_fan_out_deadline_cancels_stragglers_and_leaks_no_tasks():
    cancelled = []
    before = len(asyncio.all_tasks())

    async def worker(item):
        if item % 2 == 0:
            return item  # fast
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(item)
            raise

    loop = asyncio.get_running_loop()
    started = loop.time()
    # concurrency 2 with 3 slow items: some slow items never even start (queued behind the semaphore)
    out = await fan_out([0, 1, 3, 5, 2, 4], worker, concurrency=2, deadline_s=0.15)
    elapsed = loop.time() - started

    assert elapsed < 2
    assert out[0] == 0
    assert out[1] is UNRESOLVED and out[2] is UNRESOLVED and out[3] is UNRESOLVED
    assert cancelled  # started stragglers saw the cancellation
    assert len(asyncio.all_tasks()) == before  # reaped


async def test_fan_out_empty_input_returns_empty_list():
    async def worker(item):  # pragma: no cover - never called
        raise AssertionError

    assert await fan_out([], worker, concurrency=4, deadline_s=1) == []


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
async def test_fan_out_rejects_invalid_concurrency(bad):
    async def worker(item):  # pragma: no cover
        return item

    with pytest.raises(ValueError):
        await fan_out([1], worker, concurrency=bad, deadline_s=1)


@pytest.mark.parametrize("bad", [0, -1, None])
async def test_fan_out_rejects_invalid_deadline(bad):
    async def worker(item):  # pragma: no cover
        return item

    with pytest.raises(ValueError):
        await fan_out([1], worker, concurrency=2, deadline_s=bad)


async def test_fan_out_caller_cancellation_reaps_children():
    started = asyncio.Event()
    cancelled = []

    async def worker(item):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(item)
            raise

    before = len(asyncio.all_tasks())
    outer = asyncio.create_task(fan_out([1, 2], worker, concurrency=2, deadline_s=60))
    await started.wait()
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert sorted(cancelled) == [1, 2]
    assert len(asyncio.all_tasks()) == before


# ---------------------------------------------------------------------------
# settings / SSM / startup log
# ---------------------------------------------------------------------------


def test_settings_defaults(monkeypatch):
    for name in (
        "DOCTYPE_INFERENCE_PARALLEL_ENABLED",
        "DOCTYPE_INFERENCE_CONCURRENCY",
        "DOCTYPE_INFERENCE_DEADLINE_S",
    ):
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert s.DOCTYPE_INFERENCE_PARALLEL_ENABLED is False
    assert s.DOCTYPE_INFERENCE_CONCURRENCY == 4
    assert s.DOCTYPE_INFERENCE_DEADLINE_S == 20


def test_settings_parse_ssm_style_strings(monkeypatch):
    monkeypatch.setenv("DOCTYPE_INFERENCE_PARALLEL_ENABLED", "true")
    monkeypatch.setenv("DOCTYPE_INFERENCE_CONCURRENCY", "6")
    monkeypatch.setenv("DOCTYPE_INFERENCE_DEADLINE_S", "12.5")
    s = Settings()
    assert s.DOCTYPE_INFERENCE_PARALLEL_ENABLED is True
    assert s.DOCTYPE_INFERENCE_CONCURRENCY == 6
    assert s.DOCTYPE_INFERENCE_DEADLINE_S == 12.5


@pytest.mark.parametrize("raw", ["0", "9", "-1"])
def test_concurrency_is_validated_1_to_8(monkeypatch, raw):
    monkeypatch.setenv("DOCTYPE_INFERENCE_CONCURRENCY", raw)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("raw", ["0", "-3"])
def test_deadline_must_be_positive(monkeypatch, raw):
    monkeypatch.setenv("DOCTYPE_INFERENCE_DEADLINE_S", raw)
    with pytest.raises(ValidationError):
        Settings()


def test_ssm_mappings_exist_non_secure_and_point_at_real_settings_fields():
    mappings = {m.ssm_path: m for m in SSMParameterLoader.get_parameter_mappings()}
    expected = {
        "summary/doctype_inference_parallel_enabled": "DOCTYPE_INFERENCE_PARALLEL_ENABLED",
        "summary/doctype_inference_concurrency": "DOCTYPE_INFERENCE_CONCURRENCY",
        "summary/doctype_inference_deadline_s": "DOCTYPE_INFERENCE_DEADLINE_S",
    }
    for path, env_var in expected.items():
        assert mappings[path].env_var == env_var
        assert mappings[path].is_secure is False
        assert env_var in Settings.model_fields


def test_startup_log_line(monkeypatch, caplog):
    settings = get_settings()
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", True)
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_CONCURRENCY", 3)
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_DEADLINE_S", 20.0)
    with caplog.at_level(logging.INFO):
        log_doctype_inference_parallel_configuration()
    assert (
        "doctype_inference_parallel enabled=True concurrency=3 deadline_s=20.0"
        in caplog.text
    )


# ---------------------------------------------------------------------------
# chain
# ---------------------------------------------------------------------------


def _req(i, **kw):
    base = {
        "id": f"d{i}",
        "type_code": f"code-{i}",
        "raw_display": f"Display {i}",
        "content_title": f"Title {i}",
    }
    base.update(kw)
    return DocumentTypeInferenceRequest(**base)


def _resp(item_id, *, label=None, include=True, procedure=False, confidence=0.9):
    return DocumentTypeInferenceResponse(
        id=item_id,
        normalized_type=label or f"Type of {item_id}",
        include_for_summary=include,
        is_procedure_document=procedure,
        confidence=confidence,
    )


class FakeAgent:
    """Stands in for `agent.run`. Answers per-input-item from a deterministic function of the
    item's CONTENT (so the same item gets the same answer in a 1-item or a 5-item call), and
    records every call for sequence assertions."""

    def __init__(self, fail=None, delay=None, wrong_id=None, delay_s=0.0):
        self.calls = []  # list of raw payload strings, in call order
        self.in_flight = 0
        self.max_in_flight = 0
        self.fail = fail or {}  # item id -> exception to raise
        self.wrong_id = wrong_id or set()
        self.delay = delay or {}
        self.delay_s = delay_s

    async def run(self, payload_json):
        self.calls.append(payload_json)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            items = json.loads(payload_json)
            await asyncio.sleep(self.delay_s)
            for item in items:
                if item["id"] in self.delay:
                    await asyncio.sleep(self.delay[item["id"]])
            for item in items:
                if item["id"] in self.fail:
                    raise self.fail[item["id"]]
            out = [
                _resp(
                    "not-asked" if item["id"] in self.wrong_id else item["id"],
                    label=f"L:{item['type_code']}",
                )
                for item in items
            ]
            return SimpleNamespace(output=out)
        finally:
            self.in_flight -= 1


def _chain_with(agent):
    c = DocumentTypeInferenceChain()
    c._agent = agent
    return c


@pytest.fixture
def parallel_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", True)
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_CONCURRENCY", 4)
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_DEADLINE_S", 20.0)
    return settings


@pytest.fixture
def parallel_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "DOCTYPE_INFERENCE_PARALLEL_ENABLED", False)


def test_system_prompt_is_byte_identical_to_parent_commit():
    assert (
        hashlib.sha256(chain_module._SYSTEM_PROMPT.encode()).hexdigest()
        == PARENT_PROMPT_SHA256
    )


def test_agent_construction_unchanged():
    with (
        patch.object(chain_module, "Agent") as agent_cls,
        patch.object(chain_module, "get_pydantic_ai_model", return_value="MODEL"),
    ):
        DocumentTypeInferenceChain().agent
    args, kwargs = agent_cls.call_args
    assert args == ("MODEL",)
    assert kwargs["output_type"] == list[DocumentTypeInferenceResponse]
    assert kwargs["system_prompt"] is chain_module._SYSTEM_PROMPT
    assert dict(kwargs["model_settings"]) == {
        "temperature": 0.2,
        "timeout": 15.0,
        "max_tokens": 1200,
    }
    assert kwargs["retries"] == 1


async def test_flag_off_model_call_sequence_is_the_serial_five_item_loop(parallel_off):
    items = [_req(i) for i in range(7)]
    agent = FakeAgent()

    out = await _chain_with(agent).infer_batch(items)

    # Exactly the parent commit's sequence: ceil(7/5)=2 calls, sub-batches of 5 then 2, in order,
    # payload = json.dumps(list of model_dump(exclude_none=True)).
    expected = [
        json.dumps([i.model_dump(exclude_none=True) for i in items[0:5]]),
        json.dumps([i.model_dump(exclude_none=True) for i in items[5:7]]),
    ]
    assert agent.calls == expected
    assert agent.max_in_flight == 1
    assert [r.id for r in out] == [f"d{i}" for i in range(7)]
    # hard-coded literal for the first item's payload fragment (guards the serialisation itself)
    assert agent.calls[0].startswith(
        '[{"id": "d0", "type_code": "code-0", "category_codes": [], "content_title": "Title 0", '
        '"raw_display": "Display 0"}, {"id": "d1"'
    )


async def test_flag_off_fails_whole_request_on_id_mismatch_as_today(parallel_off):
    items = [_req(i) for i in range(3)]
    with pytest.raises(DocumentProcessingError) as exc:
        await _chain_with(FakeAgent(wrong_id={"d1"})).infer_batch(items)
    assert exc.value.reason_code == "CLASSIFICATION_ID_MISMATCH"


async def test_flag_on_makes_one_item_calls_with_same_payload_shape(parallel_on):
    items = [_req(i) for i in range(7)]
    agent = FakeAgent()

    out = await _chain_with(agent).infer_batch(items)

    assert sorted(agent.calls) == sorted(
        json.dumps([i.model_dump(exclude_none=True)]) for i in items
    )
    assert all(len(json.loads(c)) == 1 for c in agent.calls)
    assert [r.id for r in out] == [f"d{i}" for i in range(7)]  # request order


async def test_flag_on_results_equal_serial_path_for_same_model_answers(monkeypatch):
    items = [_req(i) for i in range(9)]
    settings = get_settings()
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", False)
    serial = await _chain_with(FakeAgent()).infer_batch(items)
    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", True)
    parallel = await _chain_with(FakeAgent(delay={"d0": 0.05, "d3": 0.03})).infer_batch(
        items
    )

    assert [r.model_dump() for r in parallel] == [r.model_dump() for r in serial]


async def test_flag_on_respects_concurrency_setting(parallel_on, monkeypatch):
    monkeypatch.setattr(parallel_on, "DOCTYPE_INFERENCE_CONCURRENCY", 3)
    agent = FakeAgent(delay_s=0.02)

    await _chain_with(agent).infer_batch([_req(i) for i in range(12)])

    assert len(agent.calls) == 12
    assert agent.max_in_flight == 3


async def test_flag_on_failed_item_is_omitted_and_does_not_fail_the_request(
    parallel_on, caplog
):
    items = [_req(i) for i in range(4)]
    agent = FakeAgent(fail={"d1": DocumentProcessingError("MODEL_UNAVAILABLE")})

    with caplog.at_level(logging.INFO):
        out = await _chain_with(agent).infer_batch(items)

    assert [r.id for r in out] == ["d0", "d2", "d3"]
    line = next(
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("doctype_inference_fanout")
    )
    assert line.startswith(
        "doctype_inference_fanout items=4 resolved=3 unresolved=1 concurrency=4 elapsed_ms="
    )
    assert (
        "Title" not in line and "code-" not in line
    )  # no document data in the log line


async def test_flag_on_per_item_id_mismatch_omits_only_that_item(parallel_on):
    items = [_req(i) for i in range(3)]

    out = await _chain_with(FakeAgent(wrong_id={"d1"})).infer_batch(items)

    assert [r.id for r in out] == ["d0", "d2"]


async def test_flag_on_duplicate_ids_still_rejected_before_any_call(parallel_on):
    agent = FakeAgent()
    with pytest.raises(DocumentProcessingError) as exc:
        await _chain_with(agent).infer_batch([_req(1), _req(1)])
    assert exc.value.code == "INVALID_CLASSIFICATION_BATCH"
    assert agent.calls == []


async def test_flag_on_oversized_item_rejected_before_any_call(parallel_on):
    agent = FakeAgent()
    big = _req(1, content_title="x" * 21_000)
    with pytest.raises(DocumentProcessingError) as exc:
        await _chain_with(agent).infer_batch([_req(0), big])
    assert exc.value.code == "CLASSIFICATION_INPUT_LIMIT"
    assert agent.calls == []


async def test_flag_on_all_items_failed_raises_first_items_error_like_today(
    parallel_on,
):
    items = [_req(0), _req(1)]
    agent = FakeAgent(
        fail={
            "d0": DocumentProcessingError("MODEL_AUTH_FAILED"),
            "d1": DocumentProcessingError("MODEL_UNAVAILABLE"),
        }
    )
    with pytest.raises(DocumentProcessingError) as exc:
        await _chain_with(agent).infer_batch(items)
    assert exc.value.code == "MODEL_AUTH_FAILED"


async def test_flag_on_deadline_omits_slow_items_and_returns_the_rest(
    parallel_on, monkeypatch
):
    monkeypatch.setattr(parallel_on, "DOCTYPE_INFERENCE_DEADLINE_S", 0.2)
    agent = FakeAgent(delay={"d1": 30})

    out = await _chain_with(agent).infer_batch([_req(0), _req(1), _req(2)])

    assert [r.id for r in out] == ["d0", "d2"]


async def test_flag_on_everything_past_deadline_raises_model_timeout(
    parallel_on, monkeypatch
):
    monkeypatch.setattr(parallel_on, "DOCTYPE_INFERENCE_DEADLINE_S", 0.1)
    with pytest.raises(DocumentProcessingError) as exc:
        await _chain_with(FakeAgent(delay_s=30)).infer_batch([_req(0), _req(1)])
    assert exc.value.code == "MODEL_TIMEOUT"


async def test_flag_on_empty_batch_returns_empty_without_calls(parallel_on):
    agent = FakeAgent()
    assert await _chain_with(agent).infer_batch([]) == []
    assert agent.calls == []


# ---------------------------------------------------------------------------
# route (minimal app, fake Redis)
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self, preset=None):
        self.store = dict(preset or {})
        self.sets = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, expiry=None):
        self.sets.append((key, expiry))
        self.store[key] = value


@pytest.fixture
def route_env(monkeypatch):
    """(client factory, fake redis) wired to the module-level chain via a FakeAgent."""
    redis = FakeRedis()
    monkeypatch.setattr(route_module, "redis_client", redis)
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app, raise_server_exceptions=False)

    def use_agent(agent):
        monkeypatch.setattr(route_module.chain, "_agent", agent)
        return agent

    return client, redis, use_agent


def _expected_key(item):
    canonical = json.dumps(item.model_dump(exclude={"id"}), sort_keys=True)
    return f"doctype-infer:v1:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _body(items):
    return {"items": [i.model_dump(exclude_none=True) for i in items]}


def test_route_flag_on_unresolved_item_omitted_uncached_and_cache_key_unchanged(
    route_env, parallel_on
):
    client, redis, use_agent = route_env
    items = [_req(i) for i in range(4)]
    use_agent(FakeAgent(fail={"d2": DocumentProcessingError("MODEL_UNAVAILABLE")}))

    resp = client.post(ROUTE_PATH, json=_body(items))

    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()["items"]] == [
        "d0",
        "d1",
        "d3",
    ]  # request order, d2 omitted
    written = {key for key, _ in redis.sets}
    assert written == {
        _expected_key(items[0]),
        _expected_key(items[1]),
        _expected_key(items[3]),
    }
    assert _expected_key(items[2]) not in redis.store  # unresolved is NOT cached
    assert all(expiry == 2_592_000 for _, expiry in redis.sets)


def test_route_flag_on_equals_flag_off_for_same_model_answers(route_env, monkeypatch):
    client, redis, use_agent = route_env
    items = [_req(i) for i in range(8)]
    settings = get_settings()

    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", False)
    use_agent(FakeAgent())
    off = client.post(ROUTE_PATH, json=_body(items))
    off_writes = sorted(redis.sets)
    redis.store.clear()
    redis.sets.clear()

    monkeypatch.setattr(settings, "DOCTYPE_INFERENCE_PARALLEL_ENABLED", True)
    on_agent = use_agent(FakeAgent(delay={"d0": 0.05}))
    on = client.post(ROUTE_PATH, json=_body(items))

    assert off.status_code == on.status_code == 200
    assert on.json() == off.json()
    assert sorted(redis.sets) == off_writes
    assert all(len(json.loads(c)) == 1 for c in on_agent.calls)


def test_route_cache_hits_skip_the_model_and_only_misses_fan_out(
    route_env, parallel_on
):
    client, redis, use_agent = route_env
    items = [_req(i) for i in range(3)]
    redis.store[_expected_key(items[1])] = _resp(
        "someone-else", label="Cached"
    ).model_dump_json()
    agent = use_agent(FakeAgent())

    resp = client.post(ROUTE_PATH, json=_body(items))

    data = resp.json()["items"]
    assert [r["id"] for r in data] == ["d0", "d1", "d2"]
    assert data[1]["normalized_type"] == "Cached"
    assert len(agent.calls) == 2


def test_route_flag_on_low_confidence_resolved_item_returned_but_not_cached(
    route_env, parallel_on
):
    client, redis, use_agent = route_env

    class LowConf(FakeAgent):
        async def run(self, payload_json):
            result = await super().run(payload_json)
            result.output = [
                r.model_copy(update={"confidence": 0.5}) for r in result.output
            ]
            return result

    use_agent(LowConf())
    resp = client.post(ROUTE_PATH, json=_body([_req(0)]))

    assert resp.status_code == 200 and len(resp.json()["items"]) == 1
    assert redis.sets == []


def test_route_flag_on_all_items_failed_is_500_like_today(route_env, parallel_on):
    client, redis, use_agent = route_env
    use_agent(FakeAgent(fail={"d0": DocumentProcessingError("MODEL_UNAVAILABLE")}))

    resp = client.post(ROUTE_PATH, json=_body([_req(0)]))

    assert resp.status_code == 500
    assert redis.sets == []


def test_route_flag_off_all_items_failed_is_500_today_baseline(route_env, parallel_off):
    client, redis, use_agent = route_env
    use_agent(FakeAgent(fail={"d0": DocumentProcessingError("MODEL_UNAVAILABLE")}))

    assert client.post(ROUTE_PATH, json=_body([_req(0)])).status_code == 500
