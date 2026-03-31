from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.app.common.constants.cache_keys import CACHE_KEY, chatbot_user_summaries_key
from src.app.db.models.user_profiles import UserProfile
from typing import Dict, Any, List, Optional
import json
from uuid import UUID
from src.app.db.objects.entities.patient_health_insights import PatientHealthInsights


async def cache_user_profile_and_insights(
    db: AsyncSession, user_id: str, redis_client
) -> None:
    """Cache user profile and health insights (NOT summaries/appointments — those
    come from the Node API enriched cache)."""
    user_id_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    # User profile (12h)
    user_stmt = select(UserProfile).where(UserProfile.user_id == user_id_uuid)
    user_result = await db.execute(user_stmt)
    user_profile_record = user_result.scalar_one_or_none()
    user_profile = {}
    if user_profile_record:
        user_profile = {
            "id": str(user_profile_record.id),
            "name": f"{user_profile_record.first_name} {user_profile_record.last_name}",
            "phone": user_profile_record.phone_number,
            "dob": (
                user_profile_record.date_of_birth.strftime("%Y-%m-%d")
                if user_profile_record.date_of_birth
                else None
            ),
            "language": user_profile_record.preferred_language,
            "is_active": user_profile_record.is_active,
            "zip_code": user_profile_record.zip_code,
        }
    redis_client.set(
        CACHE_KEY.CONVERSATION_USER_PROFILE.format(user_id),
        json.dumps(user_profile),
        expiry=60 * 60 * 12,
    )

    # Health insights (2h)
    health_insights_stmt = select(PatientHealthInsights).where(
        PatientHealthInsights.user_id == user_id_uuid
    )
    health_insights_result = await db.execute(health_insights_stmt)
    health_insights_orm = health_insights_result.scalars().all()
    health_insights = []
    for insight in health_insights_orm:
        health_insights.append({"insight_data": insight.insight_data})
    redis_client.set(
        CACHE_KEY.CONVERSATION_HEALTH_INSIGHTS.format(user_id),
        json.dumps(health_insights),
        expiry=60 * 60 * 2,
    )


def read_enriched_summaries(user_id: str, redis_client) -> Optional[List[Dict[str, Any]]]:
    """Read enriched summaries from the Node API cache.
    Returns None on cache miss so the caller can decide what to do."""
    key = chatbot_user_summaries_key(user_id)
    raw = redis_client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# Keep backward-compatible alias during migration
async def cache_all_user_data(
    db: AsyncSession, user_id: str, conversation_id: str, redis_client
) -> None:
    """Backward-compatible wrapper — caches profile + insights only."""
    await cache_user_profile_and_insights(db, user_id, redis_client)
