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

from src.app.services.summary_runtime import bounded_summary
from src.app.services.summary_outcomes import outcome_metadata

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

    @bounded_summary
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

        # Check ownership before any transcript text reaches an external model.
        from sqlalchemy import select, cast, String
        from src.app.db.models.appointments import Appointment
        owner = await self.db.execute(select(Appointment.id).where(
            Appointment.id == request.appointment_id,
            cast(Appointment.user_id, String) == str(request.user_id)))
        if owner.scalar_one_or_none() is None:
            raise ValueError("APPOINTMENT_SCOPE_MISMATCH")
        try:
            summary_response = await self._generate_summary(request)
            summary_data = self._prepare_summary_data(request, summary_response)
        except Exception as exc:
            from src.app.services.summary_outcomes import nonclinical_payload
            from src.app.services.summary_runtime import model_error_code
            summary_data = nonclinical_payload(request, "transcript", errors=[{"error": model_error_code(exc)}])

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
            # Pass the actual transcript text, not the request object itself (that leaked
            # UUIDs and field names into the prompt via `request`'s Python repr).
            from datetime import datetime, timezone
            def timestamp(segment):
                value = datetime.fromisoformat(segment.created_at.replace("Z", "+00:00"))
                return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            ordered = sorted(request.transcripts, key=timestamp)
            transcript_text = "\n\n".join(t.text for t in ordered)
            summary = await summarization_chain.summarize(transcript_text)

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
            self.logger.error("Transcript generation failed; error_type=%s", type(e).__name__)
            raise

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
            "diagnoses": [d.model_dump() for d in summary.medical_diagnoses_discussed],
            "instructions": summary.instructions_provided_by_provider,
            "recommendations": [
                r.model_dump() for r in summary.recommendations_provided_by_provider
            ],
            "data": {
                "procedures_mentioned": summary.procedures_mentioned,
            },
            "summary_metadata": {
                "source": "transcript",
                "transcript_count": len(request.transcripts),
                "analysis_version": "2.0",
                **outcome_metadata("complete"),
            },
        }
