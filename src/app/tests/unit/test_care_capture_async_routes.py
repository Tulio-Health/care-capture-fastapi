"""Unit tests for the two /async route handlers and the /_probe/burn route added in
routes/care_capture.py (round5-final.md sections 1.3 and 5, care-capture-nodeapi sibling
repo). Route functions are called directly (this repo's own convention for routes that
require a DB session -- see test_document_type_inference.py for the TestClient-based
alternative used where no DB dependency is involved) with authorize_summary_scope and
get_db patched out, so these stay true unit tests with no DB/network dependency.
"""

import asyncio
from types import SimpleNamespace
from typing import Generator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.models.procedure_summarization import ProcedureSummarizationRequest
from src.app.routes import care_capture
from src.app.services import async_dispatch

pytestmark = pytest.mark.asyncio


def _fake_get_db_factory(session):
    async def _fake_get_db():
        yield session

    return _fake_get_db


@pytest.fixture(autouse=True)
def patch_authorize(monkeypatch) -> None:
    monkeypatch.setattr(
        care_capture, "authorize_summary_scope", AsyncMock(return_value=None)
    )


@pytest.fixture(autouse=True)
def reset_bg_slots(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setattr(care_capture, "_bg_slots", asyncio.Semaphore(2))
    yield


def _attachment_request(**overrides):
    fields = {"appointment_id": uuid4(), "user_id": uuid4(), "async_token": "tok-abc"}
    fields.update(overrides)
    return AttachmentSummarizationRequest(**fields)


def _procedure_request(**overrides):
    fields = {"appointment_id": uuid4(), "user_id": uuid4(), "async_token": "tok-xyz"}
    fields.update(overrides)
    return ProcedureSummarizationRequest(**fields)


# ---------------------------------------------------------------------------
# 202 + echoed token + dispatch called correctly
# ---------------------------------------------------------------------------


async def test_attachment_summary_async_returns_202_and_echoes_token(
    monkeypatch,
) -> None:
    captured = {}

    def fake_dispatch(coro_factory, appointment_id, source, token):
        captured.update(
            coro_factory=coro_factory,
            appointment_id=appointment_id,
            source=source,
            token=token,
        )
        return SimpleNamespace()

    monkeypatch.setattr(care_capture, "dispatch", fake_dispatch)
    request = _attachment_request()

    response = await care_capture.attachment_summary_async(
        http_request=SimpleNamespace(), request=request, db=SimpleNamespace()
    )

    assert response == {
        "accepted": True,
        "appointment_id": str(request.appointment_id),
        "async_token": "tok-abc",
    }
    care_capture.authorize_summary_scope.assert_awaited_once()
    assert captured["appointment_id"] == request.appointment_id
    assert captured["source"] == "attachment_summary"
    assert captured["token"] == "tok-abc"


async def test_procedure_summary_async_returns_202_and_echoes_token(
    monkeypatch,
) -> None:
    captured = {}

    def fake_dispatch(coro_factory, appointment_id, source, token):
        captured.update(source=source, token=token)
        return SimpleNamespace()

    monkeypatch.setattr(care_capture, "dispatch", fake_dispatch)
    request = _procedure_request()

    response = await care_capture.procedure_summary_async(
        http_request=SimpleNamespace(), request=request, db=SimpleNamespace()
    )

    assert response == {
        "accepted": True,
        "appointment_id": str(request.appointment_id),
        "async_token": "tok-xyz",
    }
    assert captured["source"] == "procedure_summary"
    assert captured["token"] == "tok-xyz"


# ---------------------------------------------------------------------------
# Missing async_token -> 400 (belt-and-suspenders: the whole completion-signal design
# is meaningless without one, even though the field is Optional on the shared request
# model for the sync endpoints' sake)
# ---------------------------------------------------------------------------


async def test_attachment_summary_async_without_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(care_capture, "dispatch", AsyncMock())
    request = _attachment_request(async_token=None)

    with pytest.raises(HTTPException) as exc_info:
        await care_capture.attachment_summary_async(
            http_request=SimpleNamespace(), request=request, db=SimpleNamespace()
        )
    assert exc_info.value.status_code == 400
    care_capture.dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# _bg_slots busy -> immediate 503, dispatch never called
# ---------------------------------------------------------------------------


async def test_attachment_summary_async_503s_when_bg_slots_locked(monkeypatch) -> None:
    locked_semaphore = asyncio.Semaphore(0)  # already at capacity
    monkeypatch.setattr(care_capture, "_bg_slots", locked_semaphore)
    fake_dispatch = AsyncMock()
    monkeypatch.setattr(care_capture, "dispatch", fake_dispatch)
    request = _attachment_request()

    with pytest.raises(HTTPException) as exc_info:
        await care_capture.attachment_summary_async(
            http_request=SimpleNamespace(), request=request, db=SimpleNamespace()
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "SUMMARY_BUSY"
    fake_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# The dispatched background task genuinely outlives its own request/response cycle --
# proves asyncio.create_task (real dispatch, not mocked), not Starlette BackgroundTasks.
# ---------------------------------------------------------------------------


async def test_attachment_summary_async_task_outlives_request(monkeypatch) -> None:
    release = asyncio.Event()
    completed = []

    class _FakeService:
        def __init__(self, session):
            self.session = session

        async def analyze_attachments(self, request):
            await release.wait()
            completed.append(request.appointment_id)

    monkeypatch.setattr(care_capture, "AttachmentSummarizationService", _FakeService)
    monkeypatch.setattr(care_capture, "get_db", _fake_get_db_factory(SimpleNamespace()))
    # Real dispatch()/_run() run for this test (not mocked) -- avoid a real Redis dial in
    # the terminal-signal write at the end of _run.
    monkeypatch.setattr(
        async_dispatch,
        "_get_signal_redis",
        lambda: SimpleNamespace(set=lambda *a, **k: True),
    )

    request = _attachment_request()
    response = await care_capture.attachment_summary_async(
        http_request=SimpleNamespace(), request=request, db=SimpleNamespace()
    )

    assert response["accepted"] is True
    assert completed == []  # request already returned; background work still pending

    release.set()
    # Give the background task a chance to run to completion.
    for _ in range(50):
        if completed:
            break
        await asyncio.sleep(0)
    assert completed == [request.appointment_id]


# ---------------------------------------------------------------------------
# /_probe/burn: bounded seconds, internal-key-authed by virtue of not being excluded
# (covered separately against the real ClerkAuthMiddleware exclusion lists below).
# ---------------------------------------------------------------------------


def test_burn_probe_rejects_out_of_bounds_seconds() -> None:
    """seconds must be bounded [1, 300] (round6 MINOR-3: a mistyped/malicious value must
    not be able to pin a CPU thread on a prod instance indefinitely). Exercised through a
    real FastAPI request pipeline (TestClient) since Query(...) bounds are enforced at
    request-parsing time, not inside the handler body."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(care_capture.probe_router)
    client = TestClient(app)

    assert client.get("/_probe/burn", params={"seconds": 0}).status_code == 422
    assert client.get("/_probe/burn", params={"seconds": 301}).status_code == 422


async def test_burn_probe_spawns_task_and_returns_immediately(monkeypatch) -> None:
    from src.app.routes import care_capture as cc

    logged = []
    monkeypatch.setattr(cc.logger, "info", lambda *a, **k: logged.append(a))

    response = await cc.burn_probe(seconds=1)

    assert response["accepted"] is True
    assert response["seconds"] == 1
    assert "token" in response

    # Let the (short, 1s) probe task actually run to completion so it doesn't leak past
    # this test.
    probe_tasks = list(cc._probe_tasks)
    for task in probe_tasks:
        await task
    assert any("burn_probe_done" in call[0] for call in logged)


def test_probe_route_is_mounted_outside_care_capture_prefix() -> None:
    """Section 1.3's exact path is `/_probe/burn` at root -- NOT `/care-capture/_probe/
    burn` -- which is what keeps it outside ClerkAuthMiddleware's EXCLUDED_PATHS/
    EXCLUDED_PATH_PREFIXES (verified against the real list in clerk_auth.py) while still
    being reachable without the `/care-capture` router's own concerns."""
    from src.app.common.middleware.clerk_auth import ClerkAuthMiddleware

    paths = {route.path for route in care_capture.probe_router.routes}
    assert "/_probe/burn" in paths
    assert not any(
        "/_probe/burn" == excluded or "/_probe/burn".startswith(prefix)
        for excluded in ClerkAuthMiddleware.EXCLUDED_PATHS
        for prefix in ClerkAuthMiddleware.EXCLUDED_PATH_PREFIXES
    )
