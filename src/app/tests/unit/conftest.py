"""
Unit test conftest.

Overrides the session-scoped ``setup_test_database`` autouse fixture defined in
``tests/conftest.py``.  Unit tests are fully mocked and do not require a real
database connection, so the ``Base.metadata.create_all`` / ``drop_all`` calls
in the parent conftest would crash (the module-level ``engine`` property in
``database.py`` is not a proper SQLAlchemy engine object).

This fixture replaces the parent's autouse fixture with a no-op so all unit
tests in this directory can run without a live DB.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """No-op override for unit tests — no real database connection needed."""
    yield
