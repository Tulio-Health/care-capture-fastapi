"""pg_parity conftest: no application database; only the throwaway/parity PostgreSQL in PARITY_PG_DSN."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """No-op override of tests/conftest.py's autouse fixture (it needs the app engine)."""
    yield
