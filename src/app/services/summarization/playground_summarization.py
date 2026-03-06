"""Playground Summarization Service - Handles test/playground text summarization."""

from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
from src.app.common.error_models import BusinessLogicError, ExternalServiceError
from src.app.common.logging import get_logger
from src.app.models.playground_summarization import (
    PlaygroundSummarizationRequest,
    PlaygroundSummarizationResponse,
)
from src.app.models.transcript_summarization import TranscriptSummarizationResponse

logger = get_logger(__name__)


class PlaygroundSummarizationService:
    """
    Service for playground text summarization.
    
    This service handles the business logic for:
    - Validating plain text input
    - Processing text using AI summarization
    - Returning structured summaries without database storage
    
    This is designed for testing/playground purposes only.
    """

    # Text length constraints
    MIN_TEXT_LENGTH = 10
    MAX_TEXT_LENGTH = 50000

    def __init__(self):
        """Initialize the playground summarization service."""
        self.logger = logger

    async def summarize_plain_text(
        self, request: PlaygroundSummarizationRequest
    ) -> PlaygroundSummarizationResponse:
        """
        Summarize plain text for testing purposes without database storage.
        
        This method:
        1. Validates input text length and content
        2. Uses AI to generate a structured summary
        3. Returns the summary without persisting to database
        
        Args:
            request: Contains plain_text, request_id, and language_code
        
        Returns:
            PlaygroundSummarizationResponse: Structured summary with request metadata
        
        Raises:
            BusinessLogicError: If input validation fails
            ExternalServiceError: If AI summarization fails
        """
        self.logger.info(
            f"Playground summarization request started - request_id: {request.request_id}"
        )
        self.logger.debug(
            f"Request details - text_length: {len(request.plain_text) if request.plain_text else 0}, "
            f"language: {request.language_code}"
        )

        # Validate input text
        self._validate_input_text(request)

        # Generate AI summary
        summary_response = await self._generate_summary(request)

        # Build response
        response = PlaygroundSummarizationResponse(
            request_id=request.request_id, data=summary_response
        )

        # Log summary statistics
        self._log_summary_statistics(request.request_id, summary_response)

        self.logger.info(
            f"Playground summarization completed successfully - request_id: {request.request_id}"
        )

        return response

    def _validate_input_text(self, request: PlaygroundSummarizationRequest) -> None:
        """
        Validate input text meets all requirements.
        
        Args:
            request: Playground summarization request
        
        Raises:
            BusinessLogicError: If validation fails
        """
        # Check for empty or whitespace-only text
        if not request.plain_text or not request.plain_text.strip():
            self.logger.warning(
                f"Empty or whitespace-only text provided - request_id: {request.request_id}"
            )
            raise BusinessLogicError(
                message="Invalid input provided",
                details="Plain text cannot be empty or contain only whitespace",
            )

        text_length = len(request.plain_text.strip())

        # Check minimum length
        if text_length < self.MIN_TEXT_LENGTH:
            self.logger.warning(
                f"Text too short for summarization - "
                f"request_id: {request.request_id}, length: {text_length}"
            )
            raise BusinessLogicError(
                message="Text too short for summarization",
                details=f"Minimum {self.MIN_TEXT_LENGTH} characters required, got {text_length}",
            )

        # Check maximum length
        if text_length > self.MAX_TEXT_LENGTH:
            self.logger.warning(
                f"Text too long for summarization - "
                f"request_id: {request.request_id}, length: {text_length}"
            )
            raise BusinessLogicError(
                message="Text too long for summarization",
                details=f"Maximum {self.MAX_TEXT_LENGTH} characters allowed, got {text_length}",
            )

        self.logger.debug(
            f"Input validation passed - request_id: {request.request_id}, length: {text_length}"
        )

    async def _generate_summary(
        self, request: PlaygroundSummarizationRequest
    ) -> TranscriptSummarizationResponse:
        """
        Generate AI summary from plain text.
        
        Args:
            request: Playground summarization request
        
        Returns:
            TranscriptSummarizationResponse: Structured summary with medical information
        
        Raises:
            ExternalServiceError: If AI summarization fails
        """
        self.logger.info(
            f"Starting summarization process - request_id: {request.request_id}"
        )

        # Initialize summarization chain
        try:
            summarization_chain = TranscriptSummarizationChain()
        except Exception as e:
            self.logger.error(
                f"Failed to initialize summarization chain - "
                f"request_id: {request.request_id}, error: {str(e)}"
            )
            raise ExternalServiceError(
                service="TranscriptSummarizationChain",
                message="Failed to initialize summarization service",
                details=str(e),
            )

        # Generate summary
        try:
            summary = summarization_chain.summarize(request.plain_text)
            self.logger.debug(
                f"Raw summary generated - request_id: {request.request_id}"
            )
        except Exception as e:
            self.logger.error(
                f"Summarization process failed - "
                f"request_id: {request.request_id}, error: {str(e)}"
            )
            raise ExternalServiceError(
                service="OpenAI/LLM",
                message="Summarization process failed",
                details=f"Error during text processing: {str(e)}",
            )

        # Validate and parse response
        try:
            summary_model = TranscriptSummarizationResponse.model_validate_json(
                summary.model_dump_json()
            )
            self.logger.debug(
                f"Summary model validated - request_id: {request.request_id}"
            )
            return summary_model
        except Exception as e:
            self.logger.error(
                f"Summary model validation failed - "
                f"request_id: {request.request_id}, error: {str(e)}"
            )
            # Re-raise validation errors to be handled by error handlers
            raise

    def _log_summary_statistics(
        self, request_id: str, summary: TranscriptSummarizationResponse
    ) -> None:
        """
        Log statistics about the generated summary.
        
        Args:
            request_id: Request identifier for logging
            summary: Generated summary response
        """
        summary_text_length = (
            len(summary.provider_patient_discussion_summary_text)
            if summary.provider_patient_discussion_summary_text
            else 0
        )
        key_points_count = (
            len(summary.provider_patient_discussion_key_points)
            if summary.provider_patient_discussion_key_points
            else 0
        )
        medications_count = (
            len(summary.medications_prescribed_by_provider)
            if summary.medications_prescribed_by_provider
            else 0
        )

        self.logger.info(
            f"Summary generated successfully - request_id: {request_id}, "
            f"summary_length: {summary_text_length}, key_points: {key_points_count}, "
            f"medications: {medications_count}"
        )
