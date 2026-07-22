"""
PydanticAI profile agent for enterprise patient narrative generation.

Exposes:
  - profile_agent: module-level lazy Agent singleton with output_type=str.
    Produces a 2-3 paragraph clinical narrative from FHIR resources.
  - get_openai_client(): factory returning AsyncOpenAI; called at use-time so
    SSM parameters are guaranteed to be loaded before the client is created.
  - embed_text(text: str) -> list[float]: async embedding helper that truncates
    input to PROFILE_EMBED_CHAR_BUDGET (28,000 chars) and calls
    text-embedding-3-small, returning a list of 1536 floats.
  - register_pgvector_codec(): registers the pgvector asyncpg codec on the
    SQLAlchemy engine's connect event so asyncpg can serialise list[float] as
    Postgres vector type.  Called at module level (idempotent via SQLAlchemy
    event deduplication).

Usage in route handlers:
    result = await profile_agent.run(fhir_context)
    narrative: str = result.output  # NOT result.data

Threat mitigations:
  - T-02-11 (DoS via large narrative): embed_text() hard-caps input at
    PROFILE_EMBED_CHAR_BUDGET before calling OpenAI.
  - T-02-12 (codec not registered): register_pgvector_codec() called at import
    time; fallback raw-SQL path in the route handler catches codec errors.
"""

import logging

from openai import AsyncOpenAI
from pydantic_ai import Agent
from sqlalchemy import event

from src.app.common.constants.llm import LLM_MODEL
from src.app.core.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per PROF-02: narrative is truncated to this many chars before embedding to
# avoid exceeding OpenAI's input limit for text-embedding-3-small.
PROFILE_EMBED_CHAR_BUDGET: int = 28_000

# ---------------------------------------------------------------------------
# Profile agent instructions
# ---------------------------------------------------------------------------

_PROFILE_AGENT_INSTRUCTIONS = (
    "You are a clinical summary writer for an enterprise care coordination platform. "
    "Given FHIR healthcare records, write a concise 2-3 paragraph narrative patient "
    "profile suitable for enterprise care coordinators. "
    "Include key diagnoses (Condition resources), recent encounters (Encounter resources), "
    "and current medications (MedicationRequest resources). "
    "Be factual and clinical. Do not include patient names or addresses. "
    "Return only the narrative text. Do not include headers, bullet points, or markdown."
)

# ---------------------------------------------------------------------------
# Module-level profile_agent singleton (lazy-initialised)
# ---------------------------------------------------------------------------
# We defer get_pydantic_ai_model() (and therefore get_settings() / SSM access)
# until first use — keeps the module safely importable during tests and at
# startup before SSM parameters are loaded.

_profile_agent: Agent | None = None


def get_profile_agent() -> Agent:
    """Return the module-level profile_agent singleton, creating it on first call.

    Defers get_pydantic_ai_model() (and therefore get_settings() / SSM access)
    until the first request — not at import time.  This keeps the module safely
    importable during tests and at application startup before SSM parameters
    are loaded.
    """
    global _profile_agent
    if _profile_agent is None:
        from src.app.common.llm_factory import get_pydantic_ai_model

        _profile_agent = Agent(
            get_pydantic_ai_model(LLM_MODEL.GPT_4O_MINI),
            output_type=str,
            instructions=_PROFILE_AGENT_INSTRUCTIONS,
        )
    return _profile_agent


class _LazyAgent:
    """Proxy that creates the real Agent on first attribute access.

    Allows callers to do ``await profile_agent.run(...)`` without caring
    about lazy initialisation.
    """

    def __getattr__(self, name: str):
        return getattr(get_profile_agent(), name)

    def __repr__(self) -> str:  # pragma: no cover
        return repr(get_profile_agent())


profile_agent = _LazyAgent()

# ---------------------------------------------------------------------------
# OpenAI client factory
# ---------------------------------------------------------------------------


def get_openai_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI instance using the SSM-loaded API key.

    NOT a module-level singleton — called at use-time so that get_settings()
    is invoked after SSM parameters have been loaded.
    """
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def embed_text(text: str) -> list[float]:
    """Embed *text* using OpenAI text-embedding-3-small (1536 dimensions).

    Truncates input to PROFILE_EMBED_CHAR_BUDGET characters before calling
    the API to prevent exceeding OpenAI's input limit (T-02-11 mitigation).

    Returns:
        list[float] of length 1536.
    """
    truncated = text[:PROFILE_EMBED_CHAR_BUDGET]
    client = get_openai_client()
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=truncated,
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# pgvector codec registration
# ---------------------------------------------------------------------------


def register_pgvector_codec() -> None:
    """Register the pgvector asyncpg codec on the shared SQLAlchemy engine.

    Must be called before the first DB connection that writes to a VECTOR
    column.  SQLAlchemy deduplicates ``event.listens_for`` registrations on
    the same (target, event, fn) triple, so this function is idempotent.

    If the ``pgvector`` package is not installed the function is a no-op
    (fallback to raw SQL CAST(:emb AS vector) is handled in the route handler).
    """
    try:
        from pgvector.asyncpg import register_vector
    except ImportError:
        logger.debug(
            "pgvector package not available; skipping asyncpg codec registration. "
            "Route handler will fall back to raw SQL CAST(:emb AS vector)."
        )
        return

    try:
        from src.app.db.config.database import get_engine

        engine = get_engine()

        @event.listens_for(engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            dbapi_connection.run_async(register_vector)

        logger.debug("pgvector asyncpg codec registered on engine connect event.")
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "Could not register pgvector codec (engine not yet available): %s. "
            "Route handler will fall back to raw SQL CAST(:emb AS vector).",
            exc,
        )


# Register at module-import time so the codec is ready before the first
# DB connection is opened.  This matches Pitfall 4 guidance in RESEARCH.md.
register_pgvector_codec()
