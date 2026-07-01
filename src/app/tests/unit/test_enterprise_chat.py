"""
Unit tests for enterprise chat endpoints.

Covers:
- FAST-03: POST /enterprise/chat/individual returns {"answer": str}
- FAST-04: POST /enterprise/chat/population — cross-tenant isolation and SET LOCAL ordering

All tests mock the DB session and OpenAI agent; no real DB or API calls are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4, UUID

from src.app.routes.enterprise.chat import (
    IndividualChatRequest,
    PopulationChatRequest,
    individual_chat,
    population_chat,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patient_id() -> UUID:
    return uuid4()


@pytest.fixture
def account_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_db():
    """AsyncMock for AsyncSession with db.begin() context manager support."""
    db = AsyncMock()

    # db.execute() returns an AsyncMock whose .fetchall() returns an empty list by default
    execute_result = AsyncMock()
    execute_result.fetchall = MagicMock(return_value=[])
    db.execute = AsyncMock(return_value=execute_result)

    # db.begin() must work as an async context manager
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=begin_ctx)

    return db


@pytest.fixture
def sample_fhir() -> list[dict]:
    return [
        {"resourceType": "Encounter", "period": {"start": "2024-06-01"}},
        {"resourceType": "Encounter", "period": {"start": "2024-05-01"}},
    ]


# ---------------------------------------------------------------------------
# Test 1 — individual chat returns answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_individual_chat_returns_answer(patient_id, account_id, mock_db, sample_fhir):
    """POST /enterprise/chat/individual with mock agent returns response containing
    'answer' key with string value (FAST-03)."""
    with patch(
        "src.app.routes.enterprise.chat.individual_chat_agent"
    ) as mock_agent:
        mock_agent.run = AsyncMock(return_value=MagicMock(output="Patient is stable."))

        request = IndividualChatRequest(
            patient_user_id=patient_id,
            enterprise_account_id=account_id,
            query="What is the patient's recent encounter status?",
            fhir_resources=sample_fhir,
        )
        result = await individual_chat(request, mock_db)

    assert "answer" in result
    assert result["answer"] == "Patient is stable."


# ---------------------------------------------------------------------------
# Test 2 — individual chat calls prepare_fhir_context (FHIR cap enforced)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_individual_fhir_cap(patient_id, account_id, mock_db):
    """prepare_fhir_context must be called on the raw fhir_resources list;
    it performs the 8,000-char truncation (SIG-02/D-03)."""
    large_fhir = [
        {"resourceType": "Encounter", "period": {"start": "2024-01-01"}}
        for _ in range(60)
    ]

    with patch(
        "src.app.routes.enterprise.chat.prepare_fhir_context",
        return_value="truncated_context",
    ) as mock_prepare, patch(
        "src.app.routes.enterprise.chat.individual_chat_agent"
    ) as mock_agent:
        mock_agent.run = AsyncMock(return_value=MagicMock(output="ok"))

        request = IndividualChatRequest(
            patient_user_id=patient_id,
            enterprise_account_id=account_id,
            query="Summarise.",
            fhir_resources=large_fhir,
        )
        await individual_chat(request, mock_db)

    assert mock_prepare.called, "prepare_fhir_context must be called to enforce 8,000-char cap"
    args, _ = mock_prepare.call_args
    assert len(args[0]) == 60  # raw list is passed through; prepare_fhir_context does the filtering


# ---------------------------------------------------------------------------
# Test 3 — population chat cross-tenant isolation (WHERE clause)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_population_cross_tenant_isolation(account_id, mock_db):
    """The SELECT SQL must contain WHERE enterprise_account_id = :eid and the
    eid param must equal the requesting account's ID — not another account's ID (FAST-04)."""

    # Capture all db.execute() calls so we can inspect the SQL
    execute_calls: list[tuple] = []

    async def capturing_execute(stmt, params=None):
        sql_text = str(stmt) if hasattr(stmt, "__str__") else stmt
        execute_calls.append((sql_text, params))
        result = AsyncMock()
        result.fetchall = MagicMock(return_value=[])
        return result

    mock_db.execute = capturing_execute

    with patch(
        "src.app.routes.enterprise.chat.embed_text",
        new_callable=AsyncMock,
        return_value=[0.1] * 1536,
    ), patch(
        "src.app.routes.enterprise.chat.population_chat_agent"
    ) as mock_agent:
        mock_agent.run = AsyncMock(return_value=MagicMock(output="population answer"))

        request = PopulationChatRequest(
            enterprise_account_id=account_id,
            query="How many patients have diabetes?",
        )
        result = await population_chat(request, mock_db)

    # Find the SELECT call (contains enterprise_patient_profiles)
    select_calls = [
        (sql, params)
        for sql, params in execute_calls
        if "enterprise_patient_profiles" in str(sql)
    ]
    assert select_calls, "Expected a SELECT against enterprise_patient_profiles"

    select_sql, select_params = select_calls[0]
    sql_str = str(select_sql).upper()
    assert "WHERE ENTERPRISE_ACCOUNT_ID = :EID" in sql_str, (
        f"WHERE enterprise_account_id = :eid not found in SQL: {select_sql}"
    )
    assert select_params["eid"] == str(account_id), (
        f"Expected eid={account_id}, got {select_params.get('eid')}"
    )

    assert result["answer"] == "population answer"
    assert isinstance(result["patient_ids_used"], list)


# ---------------------------------------------------------------------------
# Test 4 — population chat SET LOCAL called before SELECT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_population_set_local_called(account_id, mock_db):
    """SET LOCAL app.enterprise_account_id must be the first db.execute() call
    inside the transaction, issued before the vector SELECT (RESEARCH.md Pitfall 2)."""

    execute_calls: list[tuple] = []

    async def capturing_execute(stmt, params=None):
        sql_text = str(stmt)
        execute_calls.append((sql_text, params))
        result = AsyncMock()
        result.fetchall = MagicMock(return_value=[])
        return result

    mock_db.execute = capturing_execute

    with patch(
        "src.app.routes.enterprise.chat.embed_text",
        new_callable=AsyncMock,
        return_value=[0.1] * 1536,
    ), patch(
        "src.app.routes.enterprise.chat.population_chat_agent"
    ) as mock_agent:
        mock_agent.run = AsyncMock(return_value=MagicMock(output="ans"))

        request = PopulationChatRequest(
            enterprise_account_id=account_id,
            query="Population health summary",
        )
        await population_chat(request, mock_db)

    # The very first execute() call must be the SET LOCAL
    assert execute_calls, "Expected at least one db.execute() call"
    first_sql, first_params = execute_calls[0]
    assert "SET LOCAL app.enterprise_account_id" in first_sql, (
        f"Expected SET LOCAL as first execute call, got: {first_sql!r}"
    )
    assert first_params == {"eid": str(account_id)}, (
        f"Expected eid={account_id} in SET LOCAL params, got {first_params}"
    )
