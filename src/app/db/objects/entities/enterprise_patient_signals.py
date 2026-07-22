"""
SQLAlchemy entity for the enterprise_patient_signals table.

Column names match the Phase 1 migration exactly:
  hospitalization, er_visit, new_specialist_referral, medication_change,
  new_diagnosis, functional_decline, care_setting_change, follow_up_required

Unique constraint: uq_enterprise_patient_signals_account_patient
  enforces one signals row per (enterprise_account_id, patient_user_id) pair.
"""

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from .users import Base


class EnterprisePatientSignalsEntity(Base):
    """Stores the 8 computed clinical-change signal flags per patient per enterprise account."""

    __tablename__ = "enterprise_patient_signals"

    __table_args__ = (
        UniqueConstraint(
            "enterprise_account_id",
            "patient_user_id",
            name="uq_enterprise_patient_signals_account_patient",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default="uuid_generate_v4()",
    )
    enterprise_account_id = Column(UUID(as_uuid=True), nullable=False)
    patient_user_id = Column(UUID(as_uuid=True), nullable=False)

    # 8 clinical-change signal flags (nullable — None means "not yet computed")
    hospitalization = Column(Boolean, nullable=True)
    er_visit = Column(Boolean, nullable=True)
    new_specialist_referral = Column(Boolean, nullable=True)
    medication_change = Column(Boolean, nullable=True)
    new_diagnosis = Column(Boolean, nullable=True)
    functional_decline = Column(Boolean, nullable=True)
    care_setting_change = Column(Boolean, nullable=True)
    follow_up_required = Column(Boolean, nullable=True)

    signals_computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<EnterprisePatientSignalsEntity("
            f"id={self.id}, "
            f"enterprise_account_id={self.enterprise_account_id}, "
            f"patient_user_id={self.patient_user_id})>"
        )
