"""Step 0 (grounding-check size-gate design, round9-revision.md section 10): job-end
observability. `bounded_summary` is the one shared wrapper for every summarization job
(attachment, transcript, fhir_analysis, procedure, comprehensive, playground) -- logging here
once covers all of them, instead of duplicating the log call per caller.

These tests prove the new job-end log line carries the right budget fields and wall-clock, and
that existing behavior (return value passthrough, exception propagation, budget context
teardown) is completely unchanged.
"""
from types import SimpleNamespace as NS

import pytest

from src.app.services import summary_runtime as sr
from src.app.services.document_extraction import DocumentProcessingError


class _Service:
    @sr.bounded_summary
    async def run(self, request):
        budget = sr._current_budget.get()
        budget.input_upper_bound_bytes = 4096
        budget.provider_requests = 2
        budget.model_calls = 3
        return "ok"

    @sr.bounded_summary
    async def fail(self, request):
        raise DocumentProcessingError("MODEL_UNAVAILABLE")


def _job_end_records(caplog):
    return [r.message for r in caplog.records if r.message.startswith("budget.job_end")]


@pytest.mark.asyncio
async def test_job_end_log_carries_budget_fields_and_wall_clock(caplog):
    request = NS(timeout_seconds=30)
    with caplog.at_level("INFO", logger="src.app.services.summary_runtime"):
        result = await _Service().run(request)

    assert result == "ok"  # behavior unchanged: return value passes through
    assert sr._current_budget.get() is None  # behavior unchanged: budget torn down after job

    records = _job_end_records(caplog)
    assert len(records) == 1
    message = records[0]
    assert "input_upper_bound_bytes=4096" in message
    assert "provider_requests=2" in message
    assert "model_calls=3" in message
    # max_model_calls defaults to 64; headroom = 64 - max(3, 2) = 61
    assert "model_call_headroom=61" in message
    assert "wall_seconds=" in message


@pytest.mark.asyncio
async def test_job_end_log_still_fires_when_the_job_raises(caplog):
    """The log lives in the existing `finally` block -- it must fire on the failure path too,
    without changing what gets raised."""
    request = NS(timeout_seconds=30)
    with caplog.at_level("INFO", logger="src.app.services.summary_runtime"):
        with pytest.raises(DocumentProcessingError) as excinfo:
            await _Service().fail(request)

    assert excinfo.value.code == "MODEL_UNAVAILABLE"  # behavior unchanged: original raise wins
    assert len(_job_end_records(caplog)) == 1
    assert sr._current_budget.get() is None
