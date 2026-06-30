"""
POST /enterprise/signals/compute — enterprise clinical-change signal computation.

Accepts a FHIR resource bundle for a patient, runs the PydanticAI signal agent,
persists the results via an ON CONFLICT upsert, and returns the 8 boolean flags.

Auth: ClerkAuthMiddleware validates x-internal-service-key before this handler
runs — no additional per-route auth decorator is needed (D-12).

Threat mitigations implemented here:
- T-02-03: auth via upstream ClerkAuthMiddleware (x-internal-service-key)
- T-02-04: FHIR context capped by prepare_fhir_context() before agent call
- T-02-06: prepare_fhir_context() enforces MAX_RESOURCES=50 + CHAR_BUDGET=8000
- T-02-07: pg_insert().values() uses parameterized SQL; UUID Pydantic coercion blocks injection
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.agents.enterprise.signal_agent import ImportantChanges, signal_agent
from src.app.db.config.database import get_db
from src.app.db.objects.entities.enterprise_patient_signals import (
    EnterprisePatientSignalsEntity,
)
from src.app.services.enterprise.fhir_prep import prepare_fhir_context

router = APIRouter(prefix="/signals", tags=["enterprise-signals"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class SignalComputeRequest(BaseModel):
    """Request body for POST /enterprise/signals/compute."""

    patient_user_id: UUID
    enterprise_account_id: UUID
    fhir_resources: list[dict]


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------


async def upsert_signals(
    db: AsyncSession,
    account_id: UUID,
    patient_id: UUID,
    signals: ImportantChanges,
    computed_at: datetime,
) -> None:
    """Upsert computed signal flags into enterprise_patient_signals.

    Uses an ON CONFLICT DO UPDATE on the unique constraint
    ``uq_enterprise_patient_signals_account_patient`` so repeated calls for
    the same (account, patient) pair overwrite the previous values rather than
    inserting duplicates.
    """
    signal_values = signals.model_dump()
    stmt = (
        pg_insert(EnterprisePatientSignalsEntity)
        .values(
            enterprise_account_id=account_id,
            patient_user_id=patient_id,
            signals_computed_at=computed_at,
            **signal_values,
        )
        .on_conflict_do_update(
            constraint="uq_enterprise_patient_signals_account_patient",
            set_={
                **signal_values,
                "signals_computed_at": computed_at,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.post("/compute", status_code=200)
async def compute_signals(
    request: SignalComputeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compute clinical-change signals from FHIR resources and persist them.

    Returns a JSON object with:
    - patient_user_id: str (UUID)
    - signals: dict with 8 boolean fields
    - computed_at: ISO-8601 timestamp string
    """
    try:
        fhir_context = prepare_fhir_context(request.fhir_resources)
        prompt_str = (
            f"Analyze these FHIR resources for patient {request.patient_user_id}:\n"
            f"{fhir_context}"
        )

        result = await signal_agent.run(prompt_str)
        signals: ImportantChanges = result.output  # NOT result.data

        computed_at = datetime.now(timezone.utc)
        await upsert_signals(
            db,
            request.enterprise_account_id,
            request.patient_user_id,
            signals,
            computed_at,
        )

        return {
            "patient_user_id": str(request.patient_user_id),
            "signals": signals.model_dump(),
            "computed_at": computed_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
