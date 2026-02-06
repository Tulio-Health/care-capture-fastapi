"""Comprehensive Summarization Models - Request and response models for parallel summarization."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .conversation_summaries import ConversationSummary
from .transcript_summarization import Transcript


class ComprehensiveSummarizationRequest(BaseModel):
    """
    Request model for comprehensive summarization.

    This model supports executing both transcript summarization and FHIR analysis
    in parallel for a single appointment. At least one data source must be provided.
    """

    appointment_id: UUID = Field(..., description="ID of the appointment to summarize")
    user_id: UUID = Field(..., description="ID of the user (patient)")

    # Transcript summarization fields (optional)
    transcripts: Optional[List[Transcript]] = Field(
        None,
        description="List of transcripts to summarize. If provided, transcript summarization will be executed.",
    )

    # FHIR analysis fields (optional)
    include_fhir_analysis: bool = Field(
        default=True,  # Changed from True to False - make it opt-in
        description="Whether to include FHIR analysis. If True, will fetch and analyze FHIR resources.",
    )
    resource_types: Optional[List[str]] = Field(
        None,
        description="Optional filter for specific FHIR resource types. If None, all types are included.",
    )
    analysis_focus: Optional[str] = Field(
        None,
        description="Optional focus area for FHIR analysis (e.g., 'medication_interactions', 'diagnosis_trends')",
    )

    # Execution configuration
    timeout_seconds: Optional[int] = Field(
        default=120,
        description="Maximum execution time in seconds for all operations. Default: 120 seconds.",
        ge=10,
        le=300,
    )

    @field_validator("transcripts")
    @classmethod
    def validate_transcripts(cls, v):
        """Validate transcripts list is not empty if provided."""
        if v is not None and len(v) == 0:
            raise ValueError("transcripts list cannot be empty if provided")
        return v

    @model_validator(mode="after")
    def validate_at_least_one_source(self):
        """Ensure at least one data source is provided."""
        has_transcripts = self.transcripts is not None and len(self.transcripts) > 0
        has_fhir = self.include_fhir_analysis

        if not has_transcripts and not has_fhir:
            raise ValueError(
                "At least one data source must be provided: "
                "either 'transcripts' (with at least one transcript) or 'include_fhir_analysis=True'"
            )

        return self

    def has_transcript_data(self) -> bool:
        """Check if transcript data is available for processing."""
        return self.transcripts is not None and len(self.transcripts) > 0

    def has_fhir_data_requested(self) -> bool:
        """Check if FHIR analysis is requested."""
        return self.include_fhir_analysis


class SummarizationError(BaseModel):
    """
    Error details for a failed summarization operation.

    This model captures detailed information about failures during
    parallel summarization execution.
    """

    source: str = Field(..., description="Source of the error: 'transcript' or 'fhir_analysis'")
    error_type: str = Field(..., description="Type of error (e.g., 'ValueError', 'HTTPException', 'TimeoutError')")
    error_message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(None, description="Additional error details for debugging")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the error occurred")
    traceback: Optional[str] = Field(None, description="Stack trace for debugging (only in debug mode)")

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class SummarizationMetrics(BaseModel):
    """
    Metrics about the comprehensive summarization execution.

    Provides detailed statistics about the operation's performance
    and success rates.
    """

    total_requested: int = Field(..., description="Total number of summarizations requested")
    success_count: int = Field(..., description="Number of successful summarizations")
    error_count: int = Field(..., description="Number of failed summarizations")
    execution_time_seconds: float = Field(..., description="Total execution time in seconds")
    transcript_execution_time: Optional[float] = Field(
        None, description="Transcript summarization execution time in seconds"
    )
    fhir_execution_time: Optional[float] = Field(None, description="FHIR analysis execution time in seconds")
    partial_success: bool = Field(
        ...,
        description="True if some operations succeeded and some failed, False if all succeeded or all failed",
    )
    timeout_occurred: bool = Field(default=False, description="Whether any operation timed out")


class ComprehensiveSummarizationResponse(BaseModel):
    """
    Response model for comprehensive summarization.

    Contains summaries and fhirSummaries at the top level for easy access.
    Follows standard API response format with success, message, and error fields.
    """

    success: bool = Field(
        ...,
        description="Whether the request was processed successfully (true even for partial success)",
    )
    message: Optional[str] = Field(
        None,
        description="Optional message about the response",
    )
    summaries: List[ConversationSummary] = Field(
        default_factory=list,
        description="List of summaries from transcript analysis",
    )
    fhir_summaries: List[ConversationSummary] = Field(
        default_factory=list,
        alias="fhirSummaries",
        description="List of summaries from FHIR data analysis",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if the request failed completely",
    )

    @property
    def is_complete_success(self) -> bool:
        """Check if all requested operations succeeded."""
        has_summaries = len(self.summaries) > 0 or len(self.fhir_summaries) > 0
        return self.success and has_summaries and not self.error

    @property
    def is_complete_failure(self) -> bool:
        """Check if all requested operations failed."""
        no_summaries = len(self.summaries) == 0 and len(self.fhir_summaries) == 0
        return no_summaries and self.error is not None

    @property
    def is_partial_success(self) -> bool:
        """Check if some operations succeeded and some failed."""
        has_summaries = len(self.summaries) > 0 or len(self.fhir_summaries) > 0
        # Partial success means we have at least one summary but the message indicates some failures
        return has_summaries and self.message is not None and "partial" in self.message.lower()

    def get_transcript_summaries(self) -> List[ConversationSummary]:
        """Get all transcript summaries."""
        return self.summaries

    def get_fhir_summaries(self) -> List[ConversationSummary]:
        """Get all FHIR summaries."""
        return self.fhir_summaries

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, json_encoders={datetime: lambda v: v.isoformat(), UUID: str}
    )
