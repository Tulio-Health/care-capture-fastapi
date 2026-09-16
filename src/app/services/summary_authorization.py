"""Bind summary requests to authenticated identity before fetching clinical data."""
from fastapi import HTTPException
from sqlalchemy import select
from src.app.db.objects.entities.users import Users


async def authorize_summary_scope(http_request, patient_id, session):
    if getattr(http_request.app.state, "summary_ready", True) is False:
        raise HTTPException(status_code=503, detail="Summarization is temporarily unavailable. Please try again later.")
    identity = getattr(http_request.state, "user", None) or {}
    if not identity.get("is_authenticated"):
        raise HTTPException(status_code=401, detail="Authentication required")
    # Node is an authenticated trusted service; its existing service credential is the
    # delegation boundary. A patient header, when supplied, must match the requested scope.
    if identity.get("is_internal_service"):
        scope = identity.get("clerk_id")
        if scope in {None, "service", str(patient_id)}:
            return
    result = await session.execute(select(Users.id).where(Users.clerk_id == identity.get("clerk_id"), Users.status == "ACTIVE"))
    mapped_id = result.scalar_one_or_none()
    if mapped_id is None or str(mapped_id) != str(patient_id):
        # No caregiver grant can be inferred from the role or request body. Delegated
        # requests must use the existing authenticated Node authorization boundary.
        raise HTTPException(status_code=403, detail="Patient access denied")
