"""Unit tests for the two /async route handlers added in
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
# The temporary /_probe/burn measurement route was removed (allowlist v2 prerequisite
# (a)); it must not be mounted on the real application router set.
# ---------------------------------------------------------------------------


def test_probe_burn_route_is_gone() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.app import routes

    assert not hasattr(routes, "summary_probe_router")
    assert not hasattr(care_capture, "probe_router")
    assert not hasattr(care_capture, "burn_probe")

    app = FastAPI()
    app.include_router(routes.care_capture_router)
    app.include_router(routes.root_router)
    assert not any("_probe" in getattr(r, "path", "") for r in app.routes)
    assert TestClient(app).get("/_probe/burn", params={"seconds": 1}).status_code == 404
