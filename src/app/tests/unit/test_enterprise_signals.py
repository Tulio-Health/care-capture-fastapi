"""
Wave 0 stubs — tests are intentionally failing until implementation plans complete.

Covers: FAST-01 (POST /enterprise/signals/compute endpoint), SIG-01 (signal upsert).
These stubs will remain red until Plan 02-02 is executed.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# This import will fail (ImportError) until routes/enterprise/signals.py is created —
# that is the intended red state for Wave 0.
from src.app.routes.enterprise import signals  # noqa: F401


def test_signals_endpoint_returns_importantchanges():
    """POST /enterprise/signals/compute returns a response with 'signals' key containing all 8 boolean fields."""
    pytest.fail("not implemented — stub for FAST-01/SIG-01: signals endpoint not yet built")


def test_hospitalization_flag():
    """When mock agent output has hospitalization=True, response['signals']['hospitalization'] is True."""
    pytest.fail("not implemented — stub for SIG-01: signal field mapping not yet wired")


def test_signals_upsert_called():
    """upsert_signals is called exactly once with the correct enterprise_account_id and patient_user_id."""
    pytest.fail("not implemented — stub for SIG-01: upsert not yet implemented")
