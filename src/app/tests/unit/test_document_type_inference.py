"""Unit tests for the batch-shaped document-type-inference endpoint and models.

Covers (per plan Task 2 item f):
  (1) request/response Pydantic model validation, adapted for the batch wrapper
  (2) all-cache-hit behavior with id-overwrite proof
  (3) mixed cache-hit/cache-miss remerge, with confidence-gated cache writes
  (4) infer_batch returning fewer items than requested (graceful degrade)
  (5) auth requirement, made deterministic via a freshly-constructed ClerkAuthMiddleware
      instance (NOT the shared, ambient-state-dependent session app)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from src.app.common.middleware.clerk_auth import ClerkAuthMiddleware
from src.app.models.document_type_inference import (
    DocumentTypeInferenceBatchRequest,
    DocumentTypeInferenceRequest,
    DocumentTypeInferenceResponse,
)

ROUTE_PATH = "/care-capture/document-type-inference"


# ---------------------------------------------------------------------------
# (1) Pydantic model validation
# ---------------------------------------------------------------------------


def test_batch_request_validates_with_only_required_fields():
    """A DocumentTypeInferenceBatchRequest with a single item missing all optional fields
    still validates — every field is Optional/defaulted except `id`/`category_codes`."""
    batch = DocumentTypeInferenceBatchRequest(items=[DocumentTypeInferenceRequest(id="doc-1")])

    assert batch.items[0].id == "doc-1"
    assert batch.items[0].type_code is None
    assert batch.items[0].type_system is None
    assert batch.items[0].category_text is None
    assert batch.items[0].category_codes == []
    assert batch.items[0].content_title is None
    assert batch.items[0].content_type is None
    assert batch.items[0].raw_display is None


def test_response_confidence_outside_unit_interval_is_rejected():
    """A DocumentTypeInferenceResponse with confidence outside [0.0, 1.0] is rejected."""
    with pytest.raises(ValidationError):
        DocumentTypeInferenceResponse(
            id="doc-1", normalized_type="Progress Note", include_for_summary=True, confidence=1.5
        )
    with pytest.raises(ValidationError):
        DocumentTypeInferenceResponse(
            id="doc-1", normalized_type="Progress Note", include_for_summary=True, confidence=-0.1
        )
    # Boundary values are valid.
    DocumentTypeInferenceResponse(
        id="doc-1", normalized_type="Progress Note", include_for_summary=True, confidence=0.0
    )
    DocumentTypeInferenceResponse(
        id="doc-1", normalized_type="Progress Note", include_for_summary=True, confidence=1.0
    )


def test_batch_request_validates_with_multiple_distinct_ids():
    """A DocumentTypeInferenceBatchRequest.items with MULTIPLE items each carrying distinct id
    values validates."""
    batch = DocumentTypeInferenceBatchRequest(
        items=[
            DocumentTypeInferenceRequest(id="doc-1", type_code="11506-3", raw_display="Progress note"),
            DocumentTypeInferenceRequest(id="doc-2", raw_display="unknown", content_title="Insurance Card"),
        ]
    )

    assert [item.id for item in batch.items] == ["doc-1", "doc-2"]
    assert batch.items[0].type_code == "11506-3"
    assert batch.items[1].content_title == "Insurance Card"


# ---------------------------------------------------------------------------
# Functional tests (2)-(4) — always send a matching x-internal-service-key header, deterministic
# regardless of whether the shared app's already-built middleware instance has auth_enabled True
# or False in the running test environment (harmless either way).
# ---------------------------------------------------------------------------


@pytest.fixture
def internal_service_key_env(monkeypatch):
    key = "test-internal-service-key-doctype"
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", key)
    return key


# ---------------------------------------------------------------------------
# (2) All-cache-hit behavior + id-overwrite proof
# ---------------------------------------------------------------------------


def test_all_cache_hit_overwrites_id_and_never_invokes_infer_batch(
    test_client: TestClient, internal_service_key_env
):
    # The cached blob carries an id baked in by whatever DIFFERENT original request first wrote
    # it — id is excluded from the cache-key hash, so a hit here necessarily came from elsewhere.
    cached_response = DocumentTypeInferenceResponse(
        id="stale-id-from-a-different-original-request",
        normalized_type="Progress Note",
        include_for_summary=True,
        confidence=0.9,
    )
    cached_json = cached_response.model_dump_json()

    batch_payload = {
        "items": [
            {"id": "req-1", "type_code": "11506-3", "raw_display": "Progress note"},
            {"id": "req-2", "type_code": "18842-5", "raw_display": "Discharge summary"},
        ]
    }

    with patch("src.app.cache.redis.redis_client.get", return_value=cached_json) as mock_get, patch(
        "src.app.chains.document_type_inference.chain.DocumentTypeInferenceChain.infer_batch",
        new_callable=AsyncMock,
    ) as mock_infer_batch:
        response = test_client.post(
            ROUTE_PATH,
            json=batch_payload,
            headers={"x-internal-service-key": internal_service_key_env},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2

    returned_ids = {item["id"] for item in data["items"]}
    assert returned_ids == {"req-1", "req-2"}
    assert "stale-id-from-a-different-original-request" not in returned_ids

    mock_infer_batch.assert_not_called()
    assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# (3) Mixed cache-hit/cache-miss remerge + confidence-gated cache write
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fresh_confidence,expect_cache_write",
    [
        pytest.param(0.85, True, id="confidence-above-threshold-writes-cache"),
        pytest.param(0.5, False, id="confidence-below-threshold-skips-cache-write"),
    ],
)
def test_mixed_cache_hit_and_miss_remerges_by_id_and_gates_cache_write_on_confidence(
    test_client: TestClient, internal_service_key_env, fresh_confidence, expect_cache_write
):
    cached_response = DocumentTypeInferenceResponse(
        id="stale-id-irrelevant",
        normalized_type="Insurance Card",
        include_for_summary=False,
        confidence=0.95,
    )
    cached_json = cached_response.model_dump_json()

    fresh_response = DocumentTypeInferenceResponse(
        id="item-b",
        normalized_type="Consult Note",
        include_for_summary=True,
        confidence=fresh_confidence,
    )

    batch_payload = {
        "items": [
            {"id": "item-a", "raw_display": "unknown", "content_title": "Insurance Card - Front"},
            {"id": "item-b", "raw_display": "Consult note", "content_title": "Consult Notes 01/01/2026"},
        ]
    }

    # Route iterates batch.items in order: item-a's redis_client.get call gets the cache HIT,
    # item-b's gets the MISS.
    with patch(
        "src.app.cache.redis.redis_client.get", side_effect=[cached_json, None]
    ) as mock_get, patch("src.app.cache.redis.redis_client.set", return_value=True) as mock_set, patch(
        "src.app.chains.document_type_inference.chain.DocumentTypeInferenceChain.infer_batch",
        new_callable=AsyncMock,
        return_value=[fresh_response],
    ) as mock_infer_batch:
        response = test_client.post(
            ROUTE_PATH,
            json=batch_payload,
            headers={"x-internal-service-key": internal_service_key_env},
        )

    assert response.status_code == 200
    data = response.json()
    items_by_id = {item["id"]: item for item in data["items"]}

    assert set(items_by_id.keys()) == {"item-a", "item-b"}
    assert items_by_id["item-a"]["normalized_type"] == "Insurance Card"
    assert items_by_id["item-b"]["normalized_type"] == "Consult Note"

    # infer_batch was called ONCE, with ONLY the cache-miss item.
    mock_infer_batch.assert_awaited_once()
    called_items = mock_infer_batch.call_args[0][0]
    assert [i.id for i in called_items] == ["item-b"]
    assert mock_get.call_count == 2

    if expect_cache_write:
        mock_set.assert_called_once()
    else:
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# (4) infer_batch returns fewer items than requested — graceful degrade
# ---------------------------------------------------------------------------


def test_infer_batch_returning_fewer_items_degrades_gracefully(
    test_client: TestClient, internal_service_key_env
):
    only_response = DocumentTypeInferenceResponse(
        id="item-x",
        normalized_type="Lab Report",
        include_for_summary=True,
        confidence=0.9,
    )

    batch_payload = {
        "items": [
            {"id": "item-x", "raw_display": "Lab report"},
            {"id": "item-y", "raw_display": "unknown"},
        ]
    }

    with patch("src.app.cache.redis.redis_client.get", return_value=None), patch(
        "src.app.cache.redis.redis_client.set", return_value=True
    ), patch(
        "src.app.chains.document_type_inference.chain.DocumentTypeInferenceChain.infer_batch",
        new_callable=AsyncMock,
        return_value=[only_response],  # item-y dropped/conflated by the model
    ):
        response = test_client.post(
            ROUTE_PATH,
            json=batch_payload,
            headers={"x-internal-service-key": internal_service_key_env},
        )

    # No exception — the missing id is simply absent from the merged response.
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "item-x"


# ---------------------------------------------------------------------------
# (5) Auth requirement, made deterministic via a fresh ClerkAuthMiddleware instance.
#
# The shared session-scoped `test_client` fixture's app has a LIVE, already-built middleware
# instance whose `auth_enabled` reflects whatever the ambient environment was at first use —
# test_chat.py::test_chat_endpoint_success (zero auth headers, asserts 200) proves this is
# currently False, so it cannot be relied on for a deterministic 401 assertion. Construct a
# FRESH instance instead, after monkeypatching CLERK_PUBLIC_JWT_KEY so _initialize_jwt_key()
# deterministically sets auth_enabled=True on THAT instance.
# ---------------------------------------------------------------------------


class _DummyASGIApp:
    async def __call__(self, scope, receive, send):
        pass


def _build_http_scope(headers):
    return {
        "type": "http",
        "method": "POST",
        "path": ROUTE_PATH,
        "raw_path": ROUTE_PATH.encode("utf-8"),
        "headers": headers,
        "client": ("test", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "root_path": "",
        "http_version": "1.1",
    }


async def test_dispatch_returns_401_without_any_auth_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("CLERK_PUBLIC_JWT_KEY", "x" * 250)
    middleware = ClerkAuthMiddleware(app=_DummyASGIApp())
    assert middleware.auth_enabled is True

    request = Request(_build_http_scope(headers=[]))
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 401
    call_next.assert_not_awaited()


async def test_dispatch_passes_with_matching_internal_service_key(monkeypatch):
    monkeypatch.setenv("CLERK_PUBLIC_JWT_KEY", "x" * 250)
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "test-secret")
    middleware = ClerkAuthMiddleware(app=_DummyASGIApp())
    assert middleware.auth_enabled is True

    headers = [(b"x-internal-service-key", b"test-secret")]
    request = Request(_build_http_scope(headers=headers))
    expected_response = Response(status_code=200)
    call_next = AsyncMock(return_value=expected_response)

    response = await middleware.dispatch(request, call_next)

    call_next.assert_awaited_once()
    assert response is expected_response


def test_document_type_inference_route_not_excluded_from_auth():
    """Cheap structural check tying the isolated middleware-level tests above back to this
    specific route's applicability, without needing a full E2E request."""
    assert ROUTE_PATH not in ClerkAuthMiddleware.EXCLUDED_PATHS
    assert not any(ROUTE_PATH.startswith(prefix) for prefix in ClerkAuthMiddleware.EXCLUDED_PATH_PREFIXES)
