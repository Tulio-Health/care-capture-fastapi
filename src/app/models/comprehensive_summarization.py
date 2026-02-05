"""Comprehensive Summarization Models - Request and response models for parallel summarization."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .conversation_summaries import ConversationSummary
from .transcript_summarization import Transcript


class ComprehensiveSummarizationRequest(BaseModel):
    """
    Request model for comprehensive summarization.
    
    This model supports executing both transcript summarization and FHIR analysis
    in parallel for a single appointment. At least one data source must be provided.
    """

    appointment_id: UUID = Field(
        ..., description="ID of the appointment to summarize"
    )
    user_id: UUID = Field(..., description="ID of the user (patient)")

    # Transcript summarization fields (optional)
    transcripts: Optional[List[Transcript]] = Field(
        None,
        description="List of transcripts to summarize. If provided, transcript summarization will be executed.",
    )

    # FHIR analysis fields (optional)
    include_fhir_analysis: bool = Field(
        default=True,
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

    source: str = Field(
        ..., description="Source of the error: 'transcript' or 'fhir_analysis'"
    )
    error_type: str = Field(
        ..., description="Type of error (e.g., 'ValueError', 'HTTPException', 'TimeoutError')"
    )
    error_message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(
        None, description="Additional error details for debugging"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the error occurred"
    )
    traceback: Optional[str] = Field(
        None, description="Stack trace for debugging (only in debug mode)"
    )

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


class SummarizationMetrics(BaseModel):
    """
    Metrics about the comprehensive summarization execution.
    
    Provides detailed statistics about the operation's performance
    and success rates.
    """

    total_requested: int = Field(
        ..., description="Total number of summarizations requested"
    )
    success_count: int = Field(
        ..., description="Number of successful summarizations"
    )
    error_count: int = Field(..., description="Number of failed summarizations")
    execution_time_seconds: float = Field(
        ..., description="Total execution time in seconds"
    )
    transcript_execution_time: Optional[float] = Field(
        None, description="Transcript summarization execution time in seconds"
    )
    fhir_execution_time: Optional[float] = Field(
        None, description="FHIR analysis execution time in seconds"
    )
    partial_success: bool = Field(
        ...,
        description="True if some operations succeeded and some failed, False if all succeeded or all failed",
    )
    timeout_occurred: bool = Field(
        default=False, description="Whether any operation timed out"
    )


class ComprehensiveSummarizationResponse(BaseModel):
    """
    Response model for comprehensive summarization.
    
    Contains all successful summaries, any errors that occurred,
    and detailed metrics about the operation.
    """

    summaries: List[ConversationSummary] = Field(
        default_factory=list,
        description="List of successfully created summaries. Each has metadata.source indicating the source.",
    )
    errors: List[SummarizationError] = Field(
        default_factory=list, description="List of errors for failed operations"
    )
    metrics: SummarizationMetrics = Field(
        ..., description="Execution metrics and statistics"
    )

    @property
    def is_complete_success(self) -> bool:
        """Check if all requested operations succeeded."""
        return len(self.errors) == 0 and len(self.summaries) > 0

    @property
    def is_complete_failure(self) -> bool:
        """Check if all requested operations failed."""
        return len(self.summaries) == 0 and len(self.errors) > 0

    @property
    def is_partial_success(self) -> bool:
        """Check if some operations succeeded and some failed."""
        return len(self.summaries) > 0 and len(self.errors) > 0

    def get_summary_by_source(self, source: str) -> Optional[ConversationSummary]:
        """
        Get summary by source type.
        
        Args:
            source: Source to look for ('transcript' or 'fhir_analysis')
        
        Returns:
            ConversationSummary if found, None otherwise
        """
        for summary in self.summaries:
            if summary.metadata and summary.metadata.get("source") == source:
                return summary
        return None

    def get_error_by_source(self, source: str) -> Optional[SummarizationError]:
        """
        Get error by source type.
        
        Args:
            source: Source to look for ('transcript' or 'fhir_analysis')
        
        Returns:
            SummarizationError if found, None otherwise
        """
        for error in self.errors:
            if error.source == source:
                return error
        return None

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str}
    )
