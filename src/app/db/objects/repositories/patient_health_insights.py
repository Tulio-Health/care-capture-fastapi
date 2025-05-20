from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime

from ..entities.patient_health_insights import PatientHealthInsights

class PatientHealthInsightsRepository:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    async def create(self, user_id: UUID, health_insights: dict , month: int, year: int) -> PatientHealthInsights:
        """Create a new patient health insights record"""
        insight = PatientHealthInsights(
            user_id=user_id,
            insight_data=health_insights,
            month=month,
            year=year
        )
        self.db_session.add(insight)
        await self.db_session.commit()
        await self.db_session.refresh(insight)
        return insight

    def get_by_id(self, insight_id: UUID) -> Optional[PatientHealthInsights]:
        """Get patient health insights by id"""
        return self.db_session.query(PatientHealthInsights).filter(
            PatientHealthInsights.id == insight_id
        ).first()

    def get_by_user_id(self, user_id: UUID) -> List[PatientHealthInsights]:
        """Get all health insights for a specific user"""
        return self.db_session.query(PatientHealthInsights).filter(
            PatientHealthInsights.user_id == user_id
        ).all()

    def update(self, insight_id: UUID, health_insights: dict) -> Optional[PatientHealthInsights]:
        """Update existing health insights"""
        insight = self.get_by_id(insight_id)
        if insight:
            insight.health_insights = health_insights
            insight.updated_at = datetime.utcnow()
            self.db_session.commit()
            self.db_session.refresh(insight)
        return insight

    def delete(self, insight_id: UUID) -> bool:
        """Delete health insights by id"""
        insight = self.get_by_id(insight_id)
        if insight:
            self.db_session.delete(insight)
            self.db_session.commit()
            return True
        return False

    def delete_by_user_id(self, user_id: UUID) -> bool:
        """Delete all health insights for a specific user"""
        insights = self.get_by_user_id(user_id)
        if insights:
            for insight in insights:
                self.db_session.delete(insight)
            self.db_session.commit()
            return True
        return False