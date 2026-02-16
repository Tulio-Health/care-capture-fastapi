"""Pydantic models for attachment summarization requests and responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class DocumentAttachment(BaseModel):
    """Represents a single document attachment with extracted text."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_path": "s3://carecapture-dev-storage/emr/documents/patient123/report.pdf",
                "content_type": "application/pdf",
                "title": "Lab Results - Complete Blood Count",
                "date": "2024-01-15T10:30:00Z",
                "file_name": "lab_results_cbc.pdf",
                "size": 1024567,
                "extracted_text": "Patient: John Doe\\nTest Date: 01/15/2024\\nWBC: 7.2 K/uL...",
                "extraction_error": None,
            }
        }
    )

    file_path: str = Field(..., description="S3 file path")
    content_type: str = Field(..., description="MIME type of the document")
    title: Optional[str] = Field(None, description="Document title from FHIR metadata")
    date: Optional[datetime] = Field(
        None, description="Document date from FHIR metadata"
    )
    file_name: Optional[str] = Field(None, description="Original file name")
    size: Optional[int] = Field(None, description="File size in bytes")
    extracted_text: str = Field(..., description="Extracted text content from document")
    extraction_error: Optional[str] = Field(
        None,
        description="Error message if extraction failed (for partial success scenarios)",
    )


class AttachmentSummarizationRequest(BaseModel):
    """Request model for attachment summarization."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "appointment_id": "12345678-1234-1234-1234-123456789abc",
                "user_id": "user_2abc123",
                "encounter_id": "97954261",
            }
        }
    )

    appointment_id: UUID = Field(..., description="Appointment UUID")
    user_id: str = Field(..., description="User ID (Clerk user ID)")
    encounter_id: Optional[str] = Field(
        None, description="Optional encounter ID to filter DocumentReferences"
    )


class AttachmentSummarizationResponse(BaseModel):
    """
    Response model for attachment summarization.

    Structurally similar to FhirAnalysisResponse for consistency.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clinical_summary": "Patient presented for annual physical. Recent lab work shows controlled diabetes with HbA1c at 6.8%. Blood pressure slightly elevated at 138/88. Cholesterol levels within normal range.",
                "key_insights": [
                    "HbA1c improved from 7.2% to 6.8% indicating good diabetes management",
                    "Blood pressure trending upward over past 3 visits",
                    "Patient compliant with metformin therapy",
                ],
                "documents_analyzed": 3,
                "diagnoses_mentioned": [
                    "Type 2 Diabetes Mellitus",
                    "Essential Hypertension",
                    "Hyperlipidemia",
                ],
                "medications_mentioned": [
                    "Metformin 1000mg twice daily",
                    "Lisinopril 10mg once daily",
                    "Atorvastatin 20mg at bedtime",
                ],
                "lab_results": [
                    "HbA1c: 6.8% (target <7.0%)",
                    "Fasting Glucose: 118 mg/dL",
                    "Total Cholesterol: 182 mg/dL",
                    "LDL: 98 mg/dL",
                ],
                "recommendations": [
                    "Continue current medication regimen",
                    "Monitor blood pressure at home daily",
                    "Repeat HbA1c in 3 months",
                    "Consider increasing lisinopril if BP remains elevated",
                ],
                "risk_factors": [
                    "Trending hypertension requiring monitoring",
                    "Family history of cardiovascular disease",
                ],
                "document_metadata": [
                    {
                        "title": "Lab Results - Comprehensive Metabolic Panel",
                        "date": "2024-01-15",
                        "type": "Laboratory Report",
                        "pages": 2,
                    },
                    {
                        "title": "Progress Notes",
                        "date": "2024-01-20",
                        "type": "Clinical Note",
                        "pages": 3,
                    },
                ],
                "extraction_errors": [],
            }
        }
    )

    clinical_summary: str = Field(
        ..., description="Overall clinical summary synthesized from all documents"
    )

    key_insights: List[str] = Field(
        default_factory=list,
        description="Key clinical insights and findings from documents",
    )

    documents_analyzed: int = Field(
        ..., description="Number of documents successfully analyzed"
    )

    diagnoses_mentioned: List[str] = Field(
        default_factory=list,
        description="Diagnoses and conditions mentioned across documents",
    )

    medications_mentioned: List[str] = Field(
        default_factory=list,
        description="Medications and treatments mentioned across documents",
    )

    lab_results: List[str] = Field(
        default_factory=list, description="Laboratory results and test findings"
    )

    recommendations: List[str] = Field(
        default_factory=list,
        description="Clinical recommendations and follow-up instructions",
    )

    risk_factors: List[str] = Field(
        default_factory=list, description="Identified risk factors and concerns"
    )

    document_metadata: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Metadata about analyzed documents (title, date, type, etc.)",
    )

    extraction_errors: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of documents that failed extraction with error messages",
    )
