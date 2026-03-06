"""Transcript Summarization Service - Handles provider visit transcript summarization."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
from src.app.common.logging import get_logger
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.models.transcript_summarization import (
    TranscriptSummarizationRequest,
    TranscriptSummarizationResponse,
)

logger = get_logger(__name__)


class TranscriptSummarizationService:
    """
    Service for summarizing provider visit transcripts.
    
    This service handles the business logic for:
    - Processing transcripts using AI summarization
    - Extracting key medical information
    - Storing summaries in the database
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the transcript summarization service.
        
        Args:
            db: Database session for repository operations
        """
        self.db = db
        self.summaries_repo = ConversationSummariesRepository(db)
        self.logger = logger

    async def summarize_transcript(
        self, request: TranscriptSummarizationRequest
    ) -> ConversationSummary:
        """
        Summarize provider visit transcript and store in database.
        
        This method:
        1. Uses AI to generate a structured summary
        2. Extracts key medical information (medications, diagnoses, etc.)
        3. Stores the summary in the database
        
        Args:
            request: Contains transcript_id, appointment_id, user_id, and transcripts
        
        Returns:
            ConversationSummary: The created/updated summary document
        
        Raises:
            ValueError: If input validation fails
            Exception: If summarization or database operations fail
        """
        self.logger.info(
            f"Starting transcript summarization - "
            f"appointment_id: {request.appointment_id}, user_id: {request.user_id}"
        )

        # Generate AI summary
        summary_response = await self._generate_summary(request)

        # Prepare summary data for database
        summary_data = self._prepare_summary_data(request, summary_response)

        # Store in database
        db_summary = await self.summaries_repo.upsert(
            appointment_id=request.appointment_id, summary_data=summary_data
        )

        self.logger.info(
            f"Transcript summarization completed - "
            f"appointment_id: {request.appointment_id}, summary_id: {db_summary.id}"
        )

        return ConversationSummary.model_validate(db_summary)

    async def _generate_summary(
        self, request: TranscriptSummarizationRequest
    ) -> TranscriptSummarizationResponse:
        """
        Generate AI summary from transcripts.
        
        Args:
            request: Transcript summarization request
        
        Returns:
            TranscriptSummarizationResponse: Structured summary with medical information
        
        Raises:
            Exception: If AI summarization fails
        """
        try:
            summarization_chain = TranscriptSummarizationChain()
            summary = summarization_chain.summarize(request)
            
            # Validate and parse the response
            summary_model = TranscriptSummarizationResponse.model_validate_json(
                summary.model_dump_json()
            )
            
            self.logger.debug(
                f"AI summary generated successfully - "
                f"appointment_id: {request.appointment_id}"
            )
            
            return summary_model
            
        except Exception as e:
            self.logger.error(
                f"Failed to generate AI summary - "
                f"appointment_id: {request.appointment_id}, error: {str(e)}",
                exc_info=True
            )
            raise Exception(f"AI summarization failed: {str(e)}")

    def _prepare_summary_data(
        self,
        request: TranscriptSummarizationRequest,
        summary: TranscriptSummarizationResponse,
    ) -> dict:
        """
        Prepare summary data for database storage.
        
        Args:
            request: Original request with metadata
            summary: AI-generated summary
        
        Returns:
            dict: Formatted data ready for database insertion
        """
        return {
            "summary_text": summary.provider_patient_discussion_summary_text,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": summary.provider_patient_discussion_key_points,
            "medications": summary.medications_prescribed_by_provider,
            "diagnoses": summary.medical_diagnoses_discussed,
            "instructions": summary.instructions_provided_by_provider,
            "recommendations": summary.recommendations_provided_by_provider,
            "summary_metadata": {
                "source": "transcript",
                "transcript_count": len(request.transcripts),
                "analysis_version": "1.0",
            },
        }
