from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.app.db.models.user_profiles import UserProfile
from src.app.db.models.appointments import Appointment
from src.app.db.models.ref_cms_provider_data import RefCmsProviderData
from src.app.db.objects.entities.conversation_summaries import ConversationSummaries as ConversationSummary
from typing import Dict, Any, List
import json
from datetime import date, timedelta
from uuid import UUID

# Get all user data of last 6 months (except conversation messages which are handled by Node API)
async def cache_all_user_data(db: AsyncSession, user_id: str, conversation_id: str, redis_client) -> None:
    # Convert user_id to UUID if it's a string
    user_id_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    user_id_str = str(user_id)  # String version for models that use String columns
    
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
            "dob": user_profile_record.date_of_birth.strftime('%Y-%m-%d') if user_profile_record.date_of_birth else None,
            "language": user_profile_record.preferred_language,
            "is_active": user_profile_record.is_active,
            "zip_code": user_profile_record.zip_code
        }
    # Set value with expiry
    redis_client.set(f"user_profile:{user_id}", json.dumps(user_profile), expiry=60*60*12)

    # Calculate the day before today and 12 months ago
    yesterday = date.today() - timedelta(days=1)
    twelve_months_ago = date.today() - timedelta(days=365)

    # Appointments + providers (2h, only from the past 12 months)
    appointments_stmt = select(Appointment).where(
        Appointment.user_id == str(user_id),
        Appointment.appointment_date < yesterday,  # Only fetch appointments before today
        Appointment.appointment_date >= twelve_months_ago  # Only fetch appointments from last 12 months
    )
    appointments_result = await db.execute(appointments_stmt)
    appointments = appointments_result.scalars().all()
    formatted_appointments = []
    provider_ids = set(appt.provider_id for appt in appointments if appt.provider_id)
    providers_map = {}
    if provider_ids:
        providers_stmt = select(RefCmsProviderData).where(RefCmsProviderData.id.in_(provider_ids))
        providers_result = await db.execute(providers_stmt)
        providers_db = providers_result.scalars().all()
        for provider in providers_db:
            providers_map[str(provider.id)] = provider
    print(f"Providers map: {providers_map}")
    for appt in appointments:
        provider_info = None
        if appt.provider_id and str(appt.provider_id) in providers_map:
            provider = providers_map[str(appt.provider_id)]
            provider_info = {
                "provider_id": str(provider.id),
                "provider_first_name": provider.provider_first_name,
                "provider_last_name": provider.provider_last_name,
                "specialty": provider.pri_spec
            }
        formatted_appt = {
            "id": str(appt.id),
            "date": appt.appointment_date.isoformat() if appt.appointment_date else None,
            "time": appt.appointment_time.strftime('%H:%M:%S') if appt.appointment_time else None,
            "purpose": appt.purpose,
            "location": appt.location,
            "status": appt.status,
            **(provider_info or {})
        }
        formatted_appointments.append(formatted_appt)
    # Set value with expiry
    redis_client.set(f"appointments:{user_id}", json.dumps(formatted_appointments), expiry=60*60*2)

    # Visit summaries (2h, only from last 12 months)
    summaries_stmt = select(ConversationSummary).where(
        ConversationSummary.user_id == user_id_uuid,
        ConversationSummary.created_at >= twelve_months_ago
    )
    summaries_result = await db.execute(summaries_stmt)
    summaries_orm = summaries_result.scalars().all()
    summaries = []
    for summary in summaries_orm:
        summaries.append({
            "id": str(summary.id),
            "appointment_id": str(summary.appointment_id),
            "user_id": str(summary.user_id),
            "summary_text": summary.summary_text,
            "key_points": summary.key_points,
            "medications": summary.medications,
            "diagnoses": summary.diagnoses,
            "instructions": summary.instructions,
            "recommendations": summary.recommendations,
            "created_at": summary.created_at.isoformat() if summary.created_at else None,
            "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
            "created_by": str(summary.created_by),
            "updated_by": str(summary.updated_by) if summary.updated_by else None
        })
    # Set value with expiry
    redis_client.set(f"visit_summaries:{user_id}", json.dumps(summaries), expiry=60*60*2)
    
    # No conversation messages handling - this is done by the Node API
