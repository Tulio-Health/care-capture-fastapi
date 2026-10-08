"""Unit tests for Fix 4 step 4 (round9-revision3.md Sec 3.4): `processing_errors.py`'s
`describe_error` coercion stays as the last-resort safety net for unregistered codes, but now
logs a warning naming the offending code so the next unregistered code is visible in logs
instead of silently swallowed.
"""
import logging

from src.app.services.processing_errors import STAGES, describe_error


def test_unregistered_code_still_coerces_to_internal_processing_error_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="src.app.services.processing_errors"):
        result = describe_error("SOME_BRAND_NEW_UNREGISTERED_CODE")

    assert result["error"] == "INTERNAL_PROCESSING_ERROR"
    assert any(
        "SOME_BRAND_NEW_UNREGISTERED_CODE" in record.getMessage() for record in caplog.records
    )


def test_registered_code_passes_through_without_warning(caplog):
    registered_code = next(iter(STAGES))
    with caplog.at_level(logging.WARNING, logger="src.app.services.processing_errors"):
        result = describe_error(registered_code)

    assert result["error"] == registered_code
    assert caplog.records == []
