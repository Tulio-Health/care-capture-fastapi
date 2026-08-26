from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.app.models.attachment_summarization import RecommendationDetail


class FhirAnalysisRequest(BaseModel):
    """Request model for FHIR resource analysis"""

    appointment_id: UUID
    user_id: UUID
    resource_types: list[str] | None = Field(
        None, description="Optional filter for specific FHIR resource types. If None, all types are included."
    )
    analysis_focus: str | None = Field(
        None, description="Optional focus area for analysis (e.g., 'medication_interactions', 'diagnosis_trends')"
    )


class FhirAnalysisResponse(BaseModel):
    """Response model for FHIR resource analysis containing AI-generated insights"""

    clinical_summary: str = Field(..., description="AI-generated clinical summary of the FHIR data")
    key_insights: list[str] = Field(..., description="List of key clinical insights from the analysis")
    conditions_summary: str | None = Field(None, description="Summary of patient conditions from FHIR data")
    medications_analysis: str | None = Field(
        None, description="Analysis of patient medications and potential interactions"
    )
    observations_summary: str | None = Field(
        None, description="Summary of lab results and vital signs from observations"
    )
    risk_factors: list[str] = Field(default_factory=list, description="Identified clinical risk factors")
    recommendations: list[RecommendationDetail] = Field(
        default_factory=list, description="Clinical recommendations for follow-up care"
    )
    resource_counts: dict[str, int] = Field(default_factory=dict, description="Count of FHIR resources by type")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the analysis")
