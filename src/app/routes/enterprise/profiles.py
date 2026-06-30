"""
POST /enterprise/profiles/build — enterprise patient profile building.

Accepts a FHIR resource bundle for a patient, generates a clinical narrative
using the PydanticAI profile agent, embeds it with OpenAI text-embedding-3-small,
and upserts the embedding + narrative into enterprise_patient_profiles.

Auth: ClerkAuthMiddleware validates x-internal-service-key before this handler
runs — no additional per-route auth decorator is needed (D-12).

Threat mitigations implemented here:
  - T-02-08: auth via upstream ClerkAuthMiddleware (x-internal-service-key)
  - T-02-09: FHIR context capped by prepare_fhir_context() before agent call
  - T-02-11: embed_text() truncates narrative to 28,000 chars before OpenAI call
  - T-02-12: upsert_profile() tries pg_insert first; falls back to raw SQL
    CAST(:emb AS vector) if pgvector codec raised an unknown-type error
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.agents.enterprise.profile_agent import embed_text, profile_agent
from src.app.db.config.database import get_db
from src.app.db.objects.entities.enterprise_patient_profiles import (
    EnterprisePatientProfilesEntity,
)
from src.app.services.enterprise.fhir_prep import prepare_fhir_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["enterprise-profiles"])

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ProfileBuildRequest(BaseModel):
    """Request body for POST /enterprise/profiles/build."""

    patient_user_id: UUID
    enterprise_account_id: UUID
    fhir_resources: list[dict]


# ---------------------------------------------------------------------------
# DB helper — upsert with pgvector codec primary path + raw SQL fallback
# ---------------------------------------------------------------------------


async def upsert_profile(
    db: AsyncSession,
    account_id: UUID,
    patient_id: UUID,
    embedding: list[float],
    summary: str,
    rebuilt_at: datetime,
) -> None:
    """Upsert patient profile embedding into enterprise_patient_profiles.

    Primary path: uses pg_insert + ON CONFLICT DO UPDATE via SQLAlchemy dialect
    with the pgvector asyncpg codec to serialize list[float] as a Postgres
    vector type.

    Fallback path: if the primary path raises a "vector" type error (meaning
    the pgvector codec was not registered on this connection), falls back to a
    raw SQL INSERT with CAST(:emb AS vector) which Postgres accepts without the
    codec (per RESEARCH.md Pattern 4 raw SQL fallback and Pitfall 1).

    The upsert is idempotent — duplicate (enterprise_account_id, patient_user_id)
    pairs overwrite the previous row rather than inserting duplicates (PROF-03).

    Threat mitigation T-02-12: errors containing "vector" trigger the fallback;
    all other errors are re-raised for the caller to handle.
    """
    # Primary path — list[float] serialised by pgvector codec
    try:
        stmt = (
            pg_insert(EnterprisePatientProfilesEntity)
            .values(
                enterprise_account_id=account_id,
                patient_user_id=patient_id,
                embedding=embedding,
                profile_summary=summary,
                embedding_model="text-embedding-3-small",
                last_rebuilt_at=rebuilt_at,
            )
            .on_conflict_do_update(
                constraint="uq_enterprise_patient_profiles_account_patient",
                set_={
                    "embedding": embedding,
                    "profile_summary": summary,
                    "embedding_model": "text-embedding-3-small",
                    "last_rebuilt_at": rebuilt_at,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )
        await db.execute(stmt)
        await db.commit()
        logger.info(
            "upsert_profile: primary pg_insert path succeeded "
            "(account=%s patient=%s)",
            account_id,
            patient_id,
        )
        return
    except Exception as primary_exc:
        exc_msg = str(primary_exc).lower()
        if "vector" not in exc_msg:
            # Not a pgvector codec error — re-raise immediately
            raise

        logger.warning(
            "upsert_profile: primary path hit vector-type error (%s); "
            "falling back to raw SQL CAST(:emb AS vector) (Pitfall 1 fallback).",
            primary_exc,
        )

    # Fallback path — pass embedding as JSON string; Postgres casts it
    raw_sql = text(
        """
        INSERT INTO enterprise_patient_profiles
            (enterprise_account_id, patient_user_id, embedding,
             profile_summary, embedding_model, last_rebuilt_at)
        VALUES
            (:eid, :pid, CAST(:emb AS vector),
             :summary, :model, :rebuilt_at)
        ON CONFLICT ON CONSTRAINT uq_enterprise_patient_profiles_account_patient
        DO UPDATE SET
            embedding       = CAST(EXCLUDED.embedding AS vector),
            profile_summary = EXCLUDED.profile_summary,
            embedding_model = EXCLUDED.embedding_model,
            last_rebuilt_at = EXCLUDED.last_rebuilt_at,
            updated_at      = now()
        """
    )
    await db.execute(
        raw_sql,
        {
            "eid": str(account_id),
            "pid": str(patient_id),
            "emb": json.dumps(embedding),
            "summary": summary,
            "model": "text-embedding-3-small",
            "rebuilt_at": rebuilt_at,
        },
    )
    await db.commit()
    logger.info(
        "upsert_profile: raw SQL CAST fallback path succeeded "
        "(account=%s patient=%s)",
        account_id,
        patient_id,
    )


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.post("/build", status_code=200)
async def build_profile(
    request: ProfileBuildRequest,
    db: AsyncSession = Depends(get_db),
):
    """Build a patient profile: generate narrative, embed it, upsert the vector.

    Returns a JSON object with:
    - patient_user_id: str (UUID)
    - embedded: true
    - rebuilt_at: ISO-8601 timestamp string
    """
    try:
        # 1. Prepare FHIR context (filter, sort, cap at 50 resources, 8,000-char limit)
        fhir_context = prepare_fhir_context(request.fhir_resources)

        # 2. Generate clinical narrative via profile_agent
        narrative_result = await profile_agent.run(fhir_context)
        narrative: str = narrative_result.output  # NOT narrative_result.data

        # 3. Embed narrative (truncated to 28,000 chars, model=text-embedding-3-small)
        embedding: list[float] = await embed_text(narrative)

        # 4. Upsert embedding + narrative to enterprise_patient_profiles
        rebuilt_at = datetime.now(timezone.utc)
        await upsert_profile(
            db,
            request.enterprise_account_id,
            request.patient_user_id,
            embedding,
            narrative,
            rebuilt_at,
        )

        return {
            "patient_user_id": str(request.patient_user_id),
            "embedded": True,
            "rebuilt_at": rebuilt_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "build_profile error (account=%s patient=%s): %s",
            request.enterprise_account_id,
            request.patient_user_id,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e))
