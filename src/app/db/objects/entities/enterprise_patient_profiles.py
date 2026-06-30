"""
SQLAlchemy entity for the enterprise_patient_profiles table.

Stores per-patient narrative profile summaries and their OpenAI text-embedding-3-small
vector embeddings (1536 dimensions) for population-level similarity search.

Unique constraint: uq_enterprise_patient_profiles_account_patient
  enforces one profile row per (enterprise_account_id, patient_user_id) pair.

SECURITY NOTE (T-RLS-01 / D-06):
  Phase 3/4 consumers MUST execute:
    SET LOCAL app.enterprise_account_id = '<uuid>';
  before querying this table to enforce row-level security. The WHERE clause
  in population queries must always include:
    WHERE enterprise_account_id = :eid
  to prevent cross-tenant data leakage.
"""

from uuid import uuid4

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

# pgvector import guard: use VECTOR type if available, fall back to String
# (so the entity can always be imported even in environments without pgvector)
try:
    from pgvector.sqlalchemy import VECTOR

    _PGVECTOR_AVAILABLE = True
except ImportError:
    # Fallback: store embedding as a string (raw SQL CAST(:emb AS vector) pattern)
    # This matches RESEARCH.md Pattern 4 raw SQL fallback.
    VECTOR = None  # type: ignore[assignment,misc]
    _PGVECTOR_AVAILABLE = False

from .users import Base


def _embedding_column():
    """Return the appropriate embedding column type based on pgvector availability."""
    if _PGVECTOR_AVAILABLE and VECTOR is not None:
        return Column(VECTOR(1536), nullable=True)
    # Fallback: store as Text; application layer casts via raw SQL
    return Column(Text, nullable=True)


class EnterprisePatientProfilesEntity(Base):
    """Stores per-patient AI narrative profiles and vector embeddings."""

    __tablename__ = "enterprise_patient_profiles"

    __table_args__ = (
        UniqueConstraint(
            "enterprise_account_id",
            "patient_user_id",
            name="uq_enterprise_patient_profiles_account_patient",
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

    # Vector embedding: 1536 floats from text-embedding-3-small (D-08)
    embedding = _embedding_column()

    # Narrative profile summary produced by the profile PydanticAI agent
    profile_summary = Column(Text, nullable=True)

    # Track which embedding model was used (for future migration safety)
    embedding_model = Column(String(100), nullable=True)

    last_rebuilt_at = Column(DateTime(timezone=True), nullable=True)
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
            f"<EnterprisePatientProfilesEntity("
            f"id={self.id}, "
            f"enterprise_account_id={self.enterprise_account_id}, "
            f"patient_user_id={self.patient_user_id}, "
            f"pgvector_available={_PGVECTOR_AVAILABLE})>"
        )
