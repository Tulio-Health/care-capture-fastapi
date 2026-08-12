"""
Wave 0 stubs — tests are intentionally failing until implementation plans complete.

Covers: FAST-02 (POST /enterprise/profiles/build), PROF-01 (profile narrative),
        PROF-02 (embedding generation), PROF-03 (vector upsert idempotency).
These stubs will remain red until Plan 02-03 is executed.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# This import will fail (ImportError) until routes/enterprise/profiles.py is created —
# that is the intended red state for Wave 0.
from src.app.routes.enterprise import profiles  # noqa: F401


def test_profile_agent_returns_narrative():
    """Mock agent output for profile build returns a non-empty narrative string."""
    pytest.fail("not implemented — stub for FAST-02/PROF-01: profile endpoint not yet built")


def test_embedding_model_is_text_embedding_3_small():
    """OpenAI embeddings.create is called with model='text-embedding-3-small'."""
    pytest.fail("not implemented — stub for PROF-02: embedding model selection not yet wired")


def test_embedding_length():
    """Mock returns a list of 1536 floats; len(embedding) == 1536."""
    pytest.fail("not implemented — stub for PROF-02: embedding dimension not yet validated")


def test_upsert_idempotent():
    """Calling upsert_profile twice with the same patient_user_id raises no error (ON CONFLICT DO UPDATE)."""
    pytest.fail("not implemented — stub for PROF-03: idempotent upsert not yet implemented")
