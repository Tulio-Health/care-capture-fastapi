"""Pydantic models for procedure extraction and patient-facing summarization.

One `ProcedureSummary` is produced per source procedure document (a cardiac
catheterization report, a TEE report, an operative/surgery note, etc.) — this
mirrors `document_type_inference`'s batch shape (list in, list out) rather than
`attachment_summarization`'s map-reduce/synthesis shape, since each procedure
document describes its OWN distinct event and should not be merged/deduplicated
with another procedure's fields.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NOT_DOCUMENTED_FOLLOW_UP = "Not documented in this procedure report."


class ProcedureSummary(BaseModel):
    """Structured, patient-facing summary of a single procedure document. Only include
    information explicitly stated in the source text — never infer or fabricate."""

    source_document_title: str = Field(
        ..., description="Title of the source document as provided in the metadata"
    )
    procedure_type: str = Field(
        ...,
        description=(
            "Short, specific description of the procedure performed (e.g. 'Cardiac catheterization "
            "with coronary angioplasty and stent placement', 'Transesophageal echocardiogram (TEE)', "
            "'Aortic valve replacement (AVR) surgery'). Infer from the document content."
        ),
    )
    procedure_date: Optional[str] = Field(
        None,
        description="Date the procedure was performed, in ISO format (YYYY-MM-DD), if stated",
    )
    performed_by: List[str] = Field(
        default_factory=list,
        description=(
            "One entry per person who performed/operated the procedure, as 'Name, credentials (role)' "
            "when a role is discernible (e.g. 'Chun W. Choi, MD (surgeon)'). Do not include referring/"
            "ordering/primary-care physicians who did not themselves perform the procedure."
        ),
    )
    reason: str = Field(
        ...,
        description=(
            "Plain-language explanation, addressed to the patient ('you'/'your'), of WHY the procedure "
            "was done — based only on the documented indication/reason/pre-op diagnosis/HPI."
        ),
    )
    what_was_performed: str = Field(
        ...,
        description=(
            "Plain-language explanation, addressed to the patient ('you'/'your'), of WHAT was actually "
            "done during the procedure — the key steps and findings, translated from clinical language."
        ),
    )
    outcome: str = Field(
        ...,
        description=(
            "Plain-language explanation, addressed to the patient ('you'/'your'), of the RESULT of the "
            "procedure (e.g. success, complications, key findings/impression/conclusions)."
        ),
    )
    follow_up: str = Field(
        ...,
        description=(
            "Plain-language follow-up instructions or next steps, addressed to the patient ('you'/'your'), "
            "taken ONLY from an explicit recommendation/follow-up/disposition/discharge-instructions section "
            "of the source document. If the source document contains NO such section, this field MUST be "
            f"exactly the literal string {NOT_DOCUMENTED_FOLLOW_UP!r} — never inferred, never fabricated, "
            "never left blank."
        ),
    )
    follow_up_source_quote: Optional[str] = Field(
        None,
        description=(
            "EXACT verbatim text copied character-for-character from the source document's "
            "follow-up/recommendation/disposition/discharge-instructions section that follow_up "
            "is based on. MUST be a literal substring of the source document. null if and only "
            f"if follow_up is {NOT_DOCUMENTED_FOLLOW_UP!r}."
        ),
    )


class ProcedureSummarizationRequest(BaseModel):
    """Request model for procedure summarization."""

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
