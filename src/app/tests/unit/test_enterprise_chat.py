"""
Wave 0 stubs — tests are intentionally failing until implementation plans complete.

Covers: FAST-03 (POST /enterprise/chat/individual), FAST-04 (POST /enterprise/chat/population).
These stubs will remain red until Plan 02-04 is executed.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# This import will fail (ImportError) until routes/enterprise/chat.py is created —
# that is the intended red state for Wave 0.
from src.app.routes.enterprise import chat  # noqa: F401


def test_individual_chat_returns_string():
    """POST /enterprise/chat/individual with mock agent returns response containing 'answer' key with string value."""
    pytest.fail("not implemented — stub for FAST-03: individual chat endpoint not yet built")


def test_population_cross_tenant():
    """Mock DB returns profiles only for enterprise_account_id A; profiles for account B never appear in result."""
    pytest.fail("not implemented — stub for FAST-04: population chat cross-tenant isolation not yet enforced")
