"""Pydantic models for attachment summarization requests and responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    document_type: Optional[str] = Field(
        None,
        description="Clinical document type from FHIR metadata (e.g., 'Progress Notes', 'Consult Note')",
    )
    file_name: Optional[str] = Field(None, description="Original file name")
    size: Optional[int] = Field(None, description="File size in bytes")
    extracted_text: str = Field(..., description="Extracted text content from document")
    extraction_error: Optional[str] = Field(
        None,
        description="Error message if extraction failed (for partial success scenarios)",
    )


class DocumentSummary(BaseModel):
    """Structured clinical data extracted from a single medical document. Only include information explicitly stated in the source text."""

    source_document_title: str = Field(
        ..., description="Title of the source document as provided in the metadata"
    )
    source_document_date: Optional[str] = Field(
        None,
        description="Date of the document in ISO format (YYYY-MM-DD), from metadata or document content",
    )
    source_document_type: str = Field(
        ...,
        description=(
            "Document type inferred from content (e.g., 'Lab Report', 'Progress Note', "
            "'Discharge Summary', 'Radiology Report', 'Consultation Note', 'Operative Report'). "
            "Infer dynamically from the content."
        ),
    )
    clinical_findings: List[str] = Field(
        default_factory=list,
        description="Clinical observations, examination findings, and notable results explicitly stated in the document",
    )
    diagnoses: List[str] = Field(
        default_factory=list,
        description=(
            "Confirmed diagnoses and active conditions. Convert medical abbreviations to patient-friendly language "
            "(e.g., 'HTN' → 'High blood pressure'). Remove ICD-10 codes. Combine related diagnoses for the same condition."
        ),
    )
    medications: List[str] = Field(
        default_factory=list,
        description=(
            "Drug-based medications only — items that contain active pharmaceutical ingredients "
            "(e.g., tablets, capsules, injections, syrups, inhalers, patches, topical creams). "
            "Include dosage, frequency, and route of administration where stated. "
            "Do NOT include: oxygen therapy, IV fluids without medication additives, "
            "cold/heat packs, blood transfusions, wound care, physiotherapy, counseling, "
            "monitoring instructions, or any other non-drug clinical intervention or procedure."
        ),
    )
    lab_results: List[str] = Field(
        default_factory=list,
        description="Laboratory test results with values, units, and reference ranges. Preserve exact numerical values. Format: 'Test Name: Value Unit (Reference Range)'",
        examples=[["HbA1c: 6.8% (target <7.0%)", "WBC: 7.2 K/uL (4.5-11.0)"]],
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Clinical suggestions, advice, and follow-up plans (e.g., 'consider increasing dosage', 'repeat HbA1c in 3 months'). Do not include direct patient instructions.",
    )
    instructions: List[str] = Field(
        default_factory=list,
        description="Direct instructions given by the provider to the patient (e.g., 'take with food', 'return in 2 weeks', 'avoid heavy lifting'). Do not include clinical recommendations.",
    )
    risk_factors: List[str] = Field(
        default_factory=list,
        description="Identified risk factors and concerning findings requiring monitoring, only those explicitly stated in the document",
    )
    procedures: List[str] = Field(
        default_factory=list,
        description="Medical procedures performed or recommended, with relevant details (date, site, outcome) where stated",
    )
    vital_signs: List[str] = Field(
        default_factory=list,
        description="Vital sign measurements with values and units (e.g., 'Blood Pressure: 138/88 mmHg', 'Heart Rate: 72 bpm'). Preserve exact values.",
        examples=[["Blood Pressure: 138/88 mmHg", "Heart Rate: 72 bpm"]],
    )
    narrative_summary: str = Field(
        ...,
        description="A 2-4 sentence free-text summary capturing the overall clinical context and key findings not fully covered by the structured fields above",
    )


class AttachmentSummarizationRequest(BaseModel):
    """Request model for attachment summarization."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "appointment_id": "12345678-1234-1234-1234-123456789abc",
                "user_id": "12345678-1234-1234-1234-123456789abc",
                "encounter_id": "97954261",
            }
        }
    )

    appointment_id: UUID = Field(..., description="Appointment UUID")
    user_id: UUID = Field(..., description="User ID (primary key from users table)")
    encounter_id: Optional[str] = Field(
        None, description="Optional encounter ID to filter DocumentReferences"
    )


class AttachmentSummarizationResponse(BaseModel):
    """Unified patient-facing summary synthesized from multiple clinical document extractions. Use second person ('you', 'your'). Deduplicate across documents. Preserve conflicting values as-is."""

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
        ...,
        description=(
            "Patient-facing clinical summary. Begin with appointment date, purpose, and provider. "
            "Answer: Why did you visit? What was found? What was done? What is the diagnosis? "
            "What should you do next? Use 'you'/'your'."
        ),
    )

    key_insights: List[str] = Field(
        default_factory=list,
        description=(
            "Significant clinical findings, abnormal results, trends, and notable observations across all documents. "
            "Include relevant procedures and vital signs. Each insight is a short, clear statement."
        ),
    )

    documents_analyzed: int = Field(
        ..., description="Number of documents successfully analyzed"
    )

    diagnoses_mentioned: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all diagnoses and active conditions across all documents in patient-friendly language",
    )

    medications_mentioned: List[str] = Field(
        default_factory=list,
        description=(
            "Drug-based medications only — items with active pharmaceutical ingredients "
            "(e.g., tablets, capsules, injections, syrups, inhalers, patches). "
            "Include dosage, frequency, and route where stated. "
            "Do NOT include: oxygen therapy, IV fluids without medication additives, "
            "cold/heat packs, blood transfusions, wound care, physiotherapy, counseling, "
            "or any other non-drug clinical intervention or procedure."
        ),
    )

    lab_results: List[str] = Field(
        default_factory=list,
        description="Deduplicated laboratory test results with values, units, and reference ranges. Preserve exact numerical values.",
    )

    instructions: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all direct patient instructions from providers across all documents. Do not include clinical recommendations.",
    )

    recommendations: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all clinical recommendations and follow-up plans across all documents. Do not include direct patient instructions.",
    )

    risk_factors: List[str] = Field(
        default_factory=list,
        description="Deduplicated list of all identified risk factors and concerning findings across all documents",
    )

    document_metadata: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Metadata for each analyzed document built from source_document_title, source_document_date, and source_document_type",
    )

    extraction_errors: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of documents that failed extraction with error messages",
    )
