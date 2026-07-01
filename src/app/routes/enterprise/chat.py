"""
Enterprise chat endpoints.

POST /enterprise/chat/individual — FHIR-grounded individual patient chat (FAST-03).
POST /enterprise/chat/population — population-level chat with cosine similarity search (FAST-04).

Auth: ClerkAuthMiddleware validates x-internal-service-key before these handlers
run — no additional per-route auth decorator is needed (D-12).

Threat mitigations:
- T-CHAT-01: population_chat enforces WHERE enterprise_account_id = :eid in SQL
  before ORDER BY; SET LOCAL app.enterprise_account_id = :eid issued inside
  the same db.begin() transaction for RLS defense-in-depth (RESEARCH.md Pitfall 2).
- T-CHAT-02: FHIR resources pass through prepare_fhir_context() which caps at
  8,000 chars before reaching the agent prompt (SIG-02/D-03).
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic_ai import Agent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.agents.enterprise.profile_agent import embed_text
from src.app.common.constants.llm import LLM_MODEL
from src.app.db.config.database import get_db
from src.app.services.enterprise.fhir_prep import prepare_fhir_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POPULATION_TOP_K: int = 10

# ---------------------------------------------------------------------------
# Module-level agent singletons (lazy-initialised)
# ---------------------------------------------------------------------------
# Agents are created on first use rather than at import time. This keeps the
# module importable during tests and at startup before SSM parameters are
# loaded (same pattern as profile_agent.py).

_individual_chat_agent: Agent | None = None
_population_chat_agent: Agent | None = None


def _get_individual_chat_agent() -> Agent:
    """Return the individual-chat Agent singleton, creating it on first call."""
    global _individual_chat_agent
    if _individual_chat_agent is None:
        from src.app.common.llm_factory import get_pydantic_ai_model

        _individual_chat_agent = Agent(
            get_pydantic_ai_model(LLM_MODEL.GPT_4O_MINI),
            output_type=str,
            instructions=(
                "You are a clinical assistant for enterprise care coordinators. "
                "Answer the coordinator's question using only the provided FHIR health "
                "record context for this specific patient. "
                "If the context does not contain enough information to answer, say so clearly. "
                "Be concise, factual, and clinical. Do not speculate beyond the provided data."
            ),
        )
    return _individual_chat_agent


def _get_population_chat_agent() -> Agent:
    """Return the population-chat Agent singleton, creating it on first call."""
    global _population_chat_agent
    if _population_chat_agent is None:
        from src.app.common.llm_factory import get_pydantic_ai_model

        _population_chat_agent = Agent(
            get_pydantic_ai_model(LLM_MODEL.GPT_4O_MINI),
            output_type=str,
            instructions=(
                "You are a population health analyst for enterprise care coordinators. "
                "You are given profile summaries for the most relevant patients matching a query. "
                "Answer the coordinator's population-level question using only the provided "
                "patient profiles as context. "
                "Cite specific patient IDs when referencing individual patients. "
                "Do not speculate beyond the provided profiles."
            ),
        )
    return _population_chat_agent


class _LazyAgent:
    """Proxy that creates the real Agent singleton on first attribute access.

    Allows callers to write ``await individual_chat_agent.run(...)`` without
    caring about lazy initialisation — the same pattern used in profile_agent.py.

    Special dunder attributes that unittest.mock.patch inspects during patching
    (e.g. ``__func__``, ``__wrapped__``, ``__self__``) are deliberately blocked
    with an ``AttributeError`` so that the factory is NOT called during patching.
    This keeps the module safely patchable in unit tests without SSM.
    """

    # Attributes that mock.patch / inspect.iscoroutinefunction / asyncio probe
    # to classify the object. We must NOT delegate these to the factory (which
    # would trigger lazy initialisation before SSM is loaded).
    _PASSTHROUGH_BLOCK: frozenset[str] = frozenset(
        {
            "__func__",
            "__wrapped__",
            "__self__",
            "__code__",
            "__defaults__",
            "__partialmethod__",
            "_is_coroutine_marker",
            "_is_coroutine",
            "__asyncio_future_blocking",
        }
    )

    def __init__(self, factory):
        object.__setattr__(self, "_factory", factory)

    def __getattr__(self, name: str):
        if name in _LazyAgent._PASSTHROUGH_BLOCK:
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "_factory")(), name)

    def __repr__(self) -> str:
        return f"<_LazyAgent factory={object.__getattribute__(self, '_factory').__name__}>"


# Public module-level references — these are what tests should patch.
individual_chat_agent = _LazyAgent(_get_individual_chat_agent)
population_chat_agent = _LazyAgent(_get_population_chat_agent)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/chat", tags=["enterprise-chat"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class IndividualChatRequest(BaseModel):
    patient_user_id: UUID
    enterprise_account_id: UUID
    query: str
    fhir_resources: list[dict]


class PopulationChatRequest(BaseModel):
    enterprise_account_id: UUID
    query: str


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("/individual", status_code=200)
async def individual_chat(
    request: IndividualChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Answer a clinical question about a single patient using FHIR context.

    The FHIR context is capped at 8,000 chars by prepare_fhir_context()
    (SIG-02/D-03 mitigation) before being passed to the agent.

    Returns:
        {"answer": str}
    """
    try:
        fhir_context = prepare_fhir_context(request.fhir_resources)  # cap at 8,000 chars
        user_prompt = (
            f"Patient {request.patient_user_id}:\n{fhir_context}\n\nQuestion: {request.query}"
        )
        result = await individual_chat_agent.run(user_prompt)
        answer: str = result.output
        return {"answer": answer}
    except Exception as e:
        logger.error("individual_chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/population", status_code=200)
async def population_chat(
    request: PopulationChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Answer a population-level question using cosine similarity over stored profiles.

    Cross-tenant isolation (T-CHAT-01):
    1. WHERE enterprise_account_id = :eid is applied in SQL before ORDER BY — profiles
       from other enterprise accounts are never ranked or returned.
    2. SET LOCAL app.enterprise_account_id = :eid is issued in the same transaction
       as the SELECT, providing RLS defense-in-depth (RESEARCH.md Pitfall 2).

    Returns:
        {"answer": str, "patient_ids_used": list[str]}
    """
    try:
        # Step 1 — embed the coordinator's query
        query_embedding: list[float] = await embed_text(request.query)
        query_vec_json: str = json.dumps(query_embedding)

        # Step 2 — vector search with SET LOCAL inside a single transaction so
        # that the RLS session variable is visible to the subsequent SELECT.
        # D-09: WHERE enterprise_account_id = :eid MUST appear before ORDER BY.
        async with db.begin():
            await db.execute(
                text("SET LOCAL app.enterprise_account_id = :eid"),
                {"eid": str(request.enterprise_account_id)},
            )
            rows_result = await db.execute(
                text(
                    "SELECT patient_user_id::text, profile_summary, "
                    "embedding <=> CAST(:vec AS vector) AS dist "
                    "FROM enterprise_patient_profiles "
                    "WHERE enterprise_account_id = :eid "
                    "ORDER BY dist ASC "
                    "LIMIT :top_k"
                ),
                {
                    "vec": query_vec_json,
                    "eid": str(request.enterprise_account_id),
                    "top_k": POPULATION_TOP_K,
                },
            )
            rows = rows_result.fetchall()

        # Step 3 — build patient context and collect patient IDs
        patient_ids_used: list[str] = [row.patient_user_id for row in rows]
        profile_contexts = "\n\n".join(
            f"Patient {row.patient_user_id}:\n{row.profile_summary or ''}"
            for row in rows
        )
        if not profile_contexts:
            profile_contexts = "No patient profiles found for this enterprise account."

        # Step 4 — call population_chat_agent
        user_prompt = f"Query: {request.query}\n\nPatient Profiles:\n{profile_contexts}"
        result = await population_chat_agent.run(user_prompt)
        answer: str = result.output

        return {"answer": answer, "patient_ids_used": patient_ids_used}

    except Exception as e:
        logger.error("population_chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
