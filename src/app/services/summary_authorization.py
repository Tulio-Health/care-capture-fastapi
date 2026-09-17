"""Bind summary requests to authenticated identity and their claimed appointment before
fetching clinical data."""
from fastapi import HTTPException
from sqlalchemy import select, text
from src.app.db.objects.entities.users import Users
from src.app.db.objects.repositories.conversation_summaries import appointment_belongs_to


async def _resolve_requester_id(identity, session):
    """Map the authenticated caller's clerk_id to their internal users.id."""
    result = await session.execute(select(Users.id).where(Users.clerk_id == identity.get("clerk_id"), Users.status == "ACTIVE"))
    return result.scalar_one_or_none()


async def has_delegated_access(session, requester_id, patient_id) -> bool:
    """Direct SQL mirror of nodeapi's SharedAccessService.hasAccessToUser(): self access,
    parent-of-child-profile, or an accepted & non-revoked shared_access grant. shared_access
    and these users columns are owned by nodeapi's TypeORM migrations and aren't modeled by
    fastapi's own (deliberately minimal) Users entity, so this uses raw parameterized SQL
    rather than new ORM entities.
    """
    if str(requester_id) == str(patient_id):
        return True
    parent = await session.execute(
        text("SELECT 1 FROM users WHERE id = :patient_id AND parent_user_id = :requester_id AND is_child_profile = true"),
        {"patient_id": str(patient_id), "requester_id": str(requester_id)},
    )
    if parent.scalar_one_or_none() is not None:
        return True
    shared = await session.execute(
        text(
            "SELECT 1 FROM shared_access WHERE shared_with_user_id = :requester_id "
            "AND user_id = :patient_id AND status = 'accepted' AND access_revoked_at IS NULL"
        ),
        {"requester_id": str(requester_id), "patient_id": str(patient_id)},
    )
    return shared.scalar_one_or_none() is not None


async def authorize_summary_scope(http_request, patient_id, session, appointment_id):
    if getattr(http_request.app.state, "summary_ready", True) is False:
        raise HTTPException(status_code=503, detail="Summarization is temporarily unavailable. Please try again later.")
    identity = getattr(http_request.state, "user", None) or {}
    if not identity.get("is_authenticated"):
        raise HTTPException(status_code=401, detail="Authentication required")

    authorized = False
    # Node is an authenticated trusted service; its existing service credential is the
    # delegation boundary. A patient header, when supplied, must match the requested scope.
    if identity.get("is_internal_service"):
        scope = identity.get("clerk_id")
        if scope in {None, "service", str(patient_id)}:
            authorized = True
    if not authorized:
        requester_id = await _resolve_requester_id(identity, session)
        authorized = requester_id is not None and await has_delegated_access(session, requester_id, patient_id)
    # Unconditional for every path, including the trusted-service branch above: an authorized
    # identity is not enough on its own - the appointment being requested must actually be the
    # claimed patient's own.
    if not authorized or not await appointment_belongs_to(session, appointment_id, patient_id):
        raise HTTPException(status_code=403, detail="Patient access denied")
