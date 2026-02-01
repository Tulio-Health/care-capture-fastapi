from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
import enum
from datetime import datetime

Base = declarative_base()


class FhirResourceType(enum.Enum):
    """FHIR resource types supported in the system"""
    PATIENT = "Patient"
    ENCOUNTER = "Encounter"
    OBSERVATION = "Observation"
    CONDITION = "Condition"
    CARE_PLAN = "CarePlan"
    MEDICATION_REQUEST = "MedicationRequest"
    DIAGNOSTIC_REPORT = "DiagnosticReport"
    PROCEDURE = "Procedure"
    APPOINTMENT = "Appointment"
    DOCUMENT_REFERENCE = "DocumentReference"


class EhrProvider(enum.Enum):
    """Supported EHR provider systems"""
    CERNER = "CERNER"
    EPIC = "EPIC"
    MEDITECH = "MEDITECH"
    ALLSCRIPTS = "ALLSCRIPTS"
    ATHENAHEALTH = "ATHENAHEALTH"


class FhirResource(Base):
    """
    FHIR resources synced from EHR systems.
    
    Stores FHIR-formatted healthcare data from various EMR providers,
    maintaining references to the source EHR system and connection.
    """
    __tablename__ = "fhir_resources"
    
    # Composite indexes defined at table level
    __table_args__ = (
        Index('idx_fhir_user_resource_type', 'user_id', 'resource_type'),
        Index('idx_fhir_ehr_resource_provider', 'ehr_resource_id', 'ehr_provider_id', unique=True),
        Index('idx_fhir_last_synced', 'last_synced_at'),
    )
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    user_id = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Clerk user ID"
    )
    
    resource_type = Column(
        String,
        nullable=False,
        comment="Type of FHIR resource"
    )
    
    ehr_resource_id = Column(
        String(255),
        nullable=False,
        comment="Resource ID from EMR system"
    )
    
    ehr_connection_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Connection ID from EMR Connector"
    )
    
    data = Column(
        JSONB,
        nullable=False,
        comment="Mapped FHIR data from EMR"
    )
    
    ehr_provider = Column(
        String,
        nullable=False,
        comment="EHR provider system name"
    )
    
    ehr_provider_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        comment="EHR provider UUID from EMR Connector"
    )
    
    ehr_patient_id = Column(
        String(255),
        nullable=True,
        comment="Patient ID in EHR system"
    )
    
    last_synced_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="Timestamp of last sync from EHR"
    )
    
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="Record creation timestamp"
    )
    
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Record last update timestamp"
    )
    
    def __repr__(self):
        return (
            f"<FhirResource("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"resource_type={self.resource_type.value}, "
            f"ehr_provider={self.ehr_provider.value}"
            f")>"
        )
