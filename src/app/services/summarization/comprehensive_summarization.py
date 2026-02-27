"""Comprehensive Summarization Service - Orchestrates multiple summarization services in parallel."""

import asyncio
import traceback
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.common.logging import get_logger
from src.app.core.settings import get_settings
from src.app.db.config.database import get_session_factory
from src.app.db.models.appointments import Appointment
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository
from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.models.comprehensive_summarization import (
    ComprehensiveSummarizationRequest,
    ComprehensiveSummarizationResponse,
    SummarizationError,
    SummarizationMetrics,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.models.fhir_analysis import FhirAnalysisRequest
from src.app.models.transcript_summarization import TranscriptSummarizationRequest

from .attachment_summarization import AttachmentSummarizationService
from .fhir_analysis import FhirAnalysisService
from .transcript_summarization import TranscriptSummarizationService

logger = get_logger(__name__)
settings = get_settings()


class ComprehensiveSummarizationService:
    """
    Service for orchestrating multiple summarization operations in parallel.

    This service handles the business logic for:
    - Executing transcript summarization and FHIR analysis concurrently
    - Handling partial success scenarios
    - Tracking detailed execution metrics
    - Managing timeouts and errors gracefully

    Follows SOLID principles:
    - Single Responsibility: Only orchestrates, doesn't perform summarization
    - Open/Closed: Can easily add new summarization types
    - Dependency Inversion: Depends on service abstractions
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the comprehensive summarization service.

        Args:
            db: Database session for repository operations (not used for parallel ops)
        """
        self.db = db
        self.session_factory = get_session_factory()
        self.logger = logger

    async def execute_parallel_summarization(
        self, request: ComprehensiveSummarizationRequest
    ) -> ComprehensiveSummarizationResponse:
        """
        Execute multiple summarization operations in parallel.

        This method:
        1. Determines which summarizations to run based on available data
        2. Executes them concurrently using asyncio.gather()
        3. Handles partial success (some succeed, some fail)
        4. Returns comprehensive results with metrics

        Args:
            request: Comprehensive summarization request with all parameters

        Returns:
            ComprehensiveSummarizationResponse with summaries, errors, and metrics
        """
        start_time = datetime.utcnow()

        self.logger.info(
            f"Starting comprehensive summarization - "
            f"appointment_id: {request.appointment_id}, user_id: {request.user_id}"
        )
        self.logger.debug(
            f"Request configuration - "
            f"has_transcripts: {request.has_transcript_data()}, "
            f"include_fhir: {request.has_fhir_data_requested()}, "
            f"timeout: {request.timeout_seconds}s"
        )

        # Build list of tasks to execute and check for existing summaries
        tasks, task_sources, existing_summaries = await self._build_task_list(request)

        # If all summaries exist, return them immediately
        if not tasks and existing_summaries:
            self.logger.info(
                f"All summaries already exist - returning cached results - "
                f"appointment_id: {request.appointment_id}, "
                f"count: {len(existing_summaries)}"
            )

            # Separate existing summaries by type
            transcript_summaries = []
            fhir_summaries = []

            for summary in existing_summaries:
                source = summary.metadata.get("source") if summary.metadata else None
                if source == "transcript":
                    transcript_summaries.append(summary)
                elif source in ["fhir_analysis", "attachment_summary"]:
                    fhir_summaries.append(summary)

            # Calculate execution time
            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()

            return ComprehensiveSummarizationResponse(
                success=True,
                message=f"Retrieved {len(existing_summaries)} existing summaries",
                summaries=transcript_summaries,
                fhir_summaries=fhir_summaries,
                error=None,
            )

        if not tasks and not existing_summaries:
            self.logger.warning(
                f"No tasks to execute - appointment_id: {request.appointment_id}"
            )
            return self._build_empty_response(
                "No data sources available for summarization", start_time
            )

        self.logger.info(
            f"Executing {len(tasks)} summarization task(s) in parallel - "
            f"sources: {task_sources}, appointment_id: {request.appointment_id}"
        )

        # Execute all tasks in parallel with timeout
        results = await self._execute_tasks_with_timeout(
            tasks, task_sources, request.timeout_seconds
        )

        # Process results and build response
        transcript_summaries, fhir_summaries, error_messages = self._process_results(
            results, task_sources
        )

        # Merge existing summaries with newly created ones
        for summary in existing_summaries:
            source = summary.metadata.get("source") if summary.metadata else None
            if source == "transcript":
                transcript_summaries.append(summary)
            elif source in ["fhir_analysis", "attachment_summary"]:
                fhir_summaries.append(summary)

        # Calculate execution time
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()

        # Determine success status
        has_summaries = len(transcript_summaries) > 0 or len(fhir_summaries) > 0
        has_errors = len(error_messages) > 0

        # Build response message
        message = None
        error = None

        new_count = (
            len(transcript_summaries) + len(fhir_summaries) - len(existing_summaries)
        )
        existing_count = len(existing_summaries)

        if has_summaries and has_errors:
            message = f"Partial success: {new_count} new summaries created, {existing_count} existing summaries retrieved. {len(error_messages)} operations failed."
        elif has_summaries and existing_count > 0 and new_count > 0:
            message = f"{new_count} new summaries created, {existing_count} existing summaries retrieved"
        elif has_summaries and existing_count > 0 and new_count == 0:
            message = f"Retrieved {existing_count} existing summaries"
        elif not has_summaries and has_errors:
            error = "; ".join(error_messages)

        self.logger.info(
            f"Comprehensive summarization completed - "
            f"appointment_id: {request.appointment_id}, "
            f"transcript_summaries: {len(transcript_summaries)}, "
            f"fhir_summaries: {len(fhir_summaries)}, "
            f"existing_summaries: {existing_count}, "
            f"new_summaries: {new_count}, "
            f"errors: {len(error_messages)}, "
            f"execution_time: {execution_time:.2f}s"
        )

        return ComprehensiveSummarizationResponse(
            success=has_summaries or not has_errors,
            message=message,
            summaries=transcript_summaries,
            fhir_summaries=fhir_summaries,
            error=error,
        )

    async def _build_task_list(
        self, request: ComprehensiveSummarizationRequest
    ) -> Tuple[List, List[str], List[ConversationSummary]]:
        """
        Build list of tasks to execute based on available data.

        Checks for existing summaries first and only creates new tasks if needed.

        Args:
            request: Comprehensive summarization request

        Returns:
            Tuple of (tasks list, task source names, existing summaries list)
        """
        tasks = []
        task_sources = []
        existing_summaries = []

        # Check for transcript summarization
        if request.has_transcript_data():
            # Check if transcript summary already exists
            existing_transcript = await self._get_existing_summary(
                request, "transcript"
            )

            if existing_transcript:
                self.logger.info(
                    f"Using existing transcript summary - "
                    f"appointment_id: {request.appointment_id}, "
                    f"summary_id: {existing_transcript.id}"
                )
                existing_summaries.append(existing_transcript)
            else:
                self.logger.debug(
                    f"Adding transcript summarization task - "
                    f"transcript_count: {len(request.transcripts)}, "
                    f"appointment_id: {request.appointment_id}"
                )
                tasks.append(self._run_transcript_summarization(request))
                task_sources.append("transcript")

        # Check for FHIR data (attachments or FHIR analysis)
        if request.has_fhir_data_requested():
            # Check if attachments exist for this appointment
            has_attachments = await self._check_attachments_exist(request)

            if has_attachments:
                # Check if attachment summary already exists
                existing_attachment = await self._get_existing_summary(
                    request, "attachment_summary"
                )

                if existing_attachment:
                    self.logger.info(
                        f"Using existing attachment summary - "
                        f"appointment_id: {request.appointment_id}, "
                        f"summary_id: {existing_attachment.id}"
                    )
                    existing_summaries.append(existing_attachment)
                else:
                    self.logger.debug(
                        f"Adding attachment summarization task (attachments found) - "
                        f"appointment_id: {request.appointment_id}"
                    )
                    tasks.append(self._run_attachment_summarization(request))
                    task_sources.append("attachment_summary")
            else:
                # Only fall back to FHIR analysis if config flag is enabled
                if settings.ENABLE_FHIR_FALLBACK:
                    # Check if FHIR analysis summary already exists
                    existing_fhir = await self._get_existing_summary(
                        request, "fhir_analysis"
                    )

                    if existing_fhir:
                        self.logger.info(
                            f"Using existing FHIR analysis summary - "
                            f"appointment_id: {request.appointment_id}, "
                            f"summary_id: {existing_fhir.id}"
                        )
                        existing_summaries.append(existing_fhir)
                    else:
                        self.logger.debug(
                            f"Adding FHIR analysis task (no attachments found, fallback enabled) - "
                            f"resource_types: {request.resource_types}, "
                            f"analysis_focus: {request.analysis_focus}, "
                            f"appointment_id: {request.appointment_id}"
                        )
                        tasks.append(self._run_fhir_analysis(request))
                        task_sources.append("fhir_analysis")
                else:
                    self.logger.info(
                        f"No attachments found and FHIR fallback disabled - skipping FHIR data processing - "
                        f"appointment_id: {request.appointment_id}"
                    )

        self.logger.debug(
            f"Task list built - "
            f"task_count: {len(tasks)}, sources: {task_sources}, "
            f"existing_summaries: {len(existing_summaries)}, "
            f"appointment_id: {request.appointment_id}"
        )

        return tasks, task_sources, existing_summaries

    async def _execute_tasks_with_timeout(
        self, tasks: List, task_sources: List[str], timeout_seconds: int
    ) -> List:
        """
        Execute tasks in parallel with timeout handling.

        Args:
            tasks: List of coroutines to execute
            task_sources: List of source names for each task
            timeout_seconds: Maximum execution time in seconds

        Returns:
            List of results (can include exceptions)
        """
        self.logger.debug(
            f"Starting parallel execution - task_count: {len(tasks)}, timeout: {timeout_seconds}s"
        )

        try:
            # Execute with timeout and return_exceptions=True for partial success
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_seconds
            )

            self.logger.debug(
                f"Parallel execution completed - "
                f"result_count: {len(results)}, "
                f"exception_count: {sum(1 for r in results if isinstance(r, Exception))}"
            )

            return results

        except asyncio.TimeoutError:
            self.logger.error(
                f"Parallel execution timed out after {timeout_seconds}s - tasks: {task_sources}"
            )
            # Return timeout errors for all tasks
            return [
                asyncio.TimeoutError(f"Operation timed out after {timeout_seconds}s")
            ] * len(tasks)

    def _process_results(
        self, results: List, task_sources: List[str]
    ) -> Tuple[List[ConversationSummary], List[ConversationSummary], List[str]]:
        """
        Process parallel execution results into separate arrays.

        Separates transcript summaries from FHIR summaries and tracks errors.

        Args:
            results: List of results from asyncio.gather()
            task_sources: List of source names for each task

        Returns:
            Tuple of (transcript_summaries, fhir_summaries, error_messages)
        """
        transcript_summaries = []
        fhir_summaries = []
        error_messages = []

        self.logger.debug(f"Processing {len(results)} results from parallel execution")

        for idx, result in enumerate(results):
            source = task_sources[idx]

            if isinstance(result, Exception):
                # Handle error
                error_msg = f"{source} failed: {str(result)}"
                error_messages.append(error_msg)

                self.logger.error(
                    f"Summarization failed - source: {source}, error: {str(result)}"
                )

            elif result is not None:
                # Handle success - route to appropriate array based on source
                if source == "transcript":
                    transcript_summaries.append(result)
                    self.logger.info(
                        f"Transcript summarization succeeded - "
                        f"summary_id: {result.id if hasattr(result, 'id') else 'unknown'}"
                    )
                elif source == "fhir_analysis":
                    fhir_summaries.append(result)
                    self.logger.info(
                        f"FHIR analysis succeeded - summary_id: {result.id if hasattr(result, 'id') else 'unknown'}"
                    )
                elif source == "attachment_summary":
                    fhir_summaries.append(result)  # Store in fhir_summaries array
                    self.logger.info(
                        f"Attachment summarization succeeded - summary_id: {result.id if hasattr(result, 'id') else 'unknown'}"
                    )
            else:
                # Handle None result (shouldn't happen, but defensive)
                self.logger.warning(f"Summarization returned None - source: {source}")
                error_messages.append(f"{source}: No result returned")

        self.logger.debug(
            f"Results processed - "
            f"transcript_summaries: {len(transcript_summaries)}, "
            f"fhir_summaries: {len(fhir_summaries)}, "
            f"errors: {len(error_messages)}"
        )

        return transcript_summaries, fhir_summaries, error_messages

    async def _run_transcript_summarization(
        self, request: ComprehensiveSummarizationRequest
    ) -> Optional[ConversationSummary]:
        """
        Execute transcript summarization with its own database session.

        Args:
            request: Comprehensive summarization request

        Returns:
            ConversationSummary if successful

        Raises:
            Exception: Re-raises any exception to be caught by gather()
        """
        start_time = datetime.utcnow()

        self.logger.info(
            f"Starting transcript summarization - "
            f"appointment_id: {request.appointment_id}, "
            f"transcript_count: {len(request.transcripts or [])}"
        )

        # Create a separate database session for this operation
        async with self.session_factory() as session:
            try:
                # Create service with its own session
                transcript_service = TranscriptSummarizationService(session)

                # Build transcript-specific request
                transcript_req = TranscriptSummarizationRequest(
                    appointment_id=request.appointment_id,
                    transcripts=request.transcripts or [],
                    user_id=request.user_id,
                )

                # Execute summarization
                result = await transcript_service.summarize_transcript(transcript_req)

                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.info(
                    f"Transcript summarization completed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s"
                )

                # Add execution time to metadata
                if result.metadata:
                    result.metadata["transcript_execution_time"] = execution_time

                return result

            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.error(
                    f"Transcript summarization failed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s, "
                    f"error: {str(e)}",
                    exc_info=True,
                )
                # Re-raise to be caught by gather()
                raise

    async def _run_fhir_analysis(
        self, request: ComprehensiveSummarizationRequest
    ) -> Optional[ConversationSummary]:
        """
        Execute FHIR analysis with its own database session.

        Args:
            request: Comprehensive summarization request

        Returns:
            ConversationSummary if successful

        Raises:
            Exception: Re-raises any exception to be caught by gather()
        """
        start_time = datetime.utcnow()

        self.logger.info(
            f"Starting FHIR analysis - "
            f"appointment_id: {request.appointment_id}, "
            f"resource_types: {request.resource_types}, "
            f"analysis_focus: {request.analysis_focus}"
        )

        # Create a separate database session for this operation
        async with self.session_factory() as session:
            try:
                # Create service with its own session
                fhir_service = FhirAnalysisService(session)

                # Build FHIR-specific request
                fhir_req = FhirAnalysisRequest(
                    appointment_id=request.appointment_id,
                    user_id=request.user_id,
                    resource_types=request.resource_types,
                    analysis_focus=request.analysis_focus,
                )

                # Execute analysis
                result = await fhir_service.analyze_fhir_resources(fhir_req)

                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.info(
                    f"FHIR analysis completed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s"
                )

                # Add execution time to metadata
                if result.metadata:
                    result.metadata["fhir_execution_time"] = execution_time

                return result

            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.error(
                    f"FHIR analysis failed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s, "
                    f"error: {str(e)}",
                    exc_info=True,
                )
                # Re-raise to be caught by gather()
                raise

    async def _check_attachments_exist(
        self, request: ComprehensiveSummarizationRequest
    ) -> bool:
        """
        Check if appointment's encounter has DocumentReferences with attachments.

        Returns:
            bool: True if attachments exist, False otherwise
        """
        async with self.session_factory() as session:
            try:
                # Get appointment to find encounter_id
                appointment_stmt = select(Appointment).where(
                    Appointment.id == request.appointment_id
                )
                result = await session.execute(appointment_stmt)
                appointment = result.scalar_one_or_none()

                if not appointment or not appointment.ehr_entity_id:
                    return False

                # Check for DocumentReferences with attachments
                fhir_repo = FhirResourcesRepository(session)
                doc_refs = await fhir_repo.get_document_references_with_attachments(
                    user_id=str(request.user_id), encounter_id=appointment.ehr_entity_id
                )

                return len(doc_refs) > 0

            except Exception as e:
                self.logger.error(
                    f"Error checking attachments existence: {str(e)}", exc_info=True
                )
                return False

    async def _run_attachment_summarization(
        self, request: ComprehensiveSummarizationRequest
    ) -> Optional[ConversationSummary]:
        """
        Execute attachment summarization with its own database session.

        Args:
            request: Comprehensive summarization request

        Returns:
            ConversationSummary if successful

        Raises:
            Exception: Re-raises any exception to be caught by gather()
        """
        start_time = datetime.utcnow()

        self.logger.info(
            f"Starting attachment summarization - "
            f"appointment_id: {request.appointment_id}"
        )

        async with self.session_factory() as session:
            try:
                # Create service with its own session
                attachment_service = AttachmentSummarizationService(session)

                # Build attachment-specific request
                attachment_req = AttachmentSummarizationRequest(
                    appointment_id=request.appointment_id,
                    user_id=request.user_id,
                )

                # Execute summarization
                result = await attachment_service.analyze_attachments(attachment_req)

                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.info(
                    f"Attachment summarization completed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s"
                )

                # Add execution time to metadata
                if result.metadata:
                    result.metadata["attachment_execution_time"] = execution_time

                return result

            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                self.logger.error(
                    f"Attachment summarization failed - "
                    f"appointment_id: {request.appointment_id}, "
                    f"execution_time: {execution_time:.2f}s, "
                    f"error: {str(e)}",
                    exc_info=True,
                )
                # Re-raise to be caught by gather()
                raise

    async def _get_existing_summary(
        self, request: ComprehensiveSummarizationRequest, source: str
    ) -> Optional[ConversationSummary]:
        """
        Check if a summary already exists for this appointment and source type.

        Args:
            request: Comprehensive summarization request
            source: Summary source type ('attachment_summary', 'fhir_analysis', 'transcript')

        Returns:
            ConversationSummary if exists, None otherwise
        """
        async with self.session_factory() as session:
            try:
                summaries_repo = ConversationSummariesRepository(session)

                existing_summary = (
                    await summaries_repo.get_by_appointment_id_and_source(
                        appointment_id=request.appointment_id, source=source
                    )
                )

                if existing_summary:
                    self.logger.info(
                        f"Found existing {source} summary - "
                        f"appointment_id: {request.appointment_id}, "
                        f"summary_id: {existing_summary.id}"
                    )

                    # Convert database entity to Pydantic model
                    return ConversationSummary(
                        id=existing_summary.id,
                        user_id=existing_summary.user_id,
                        appointment_id=existing_summary.appointment_id,
                        summary_text=existing_summary.summary_text,
                        #summary_type=existing_summary.summary_type,
                        summary_type = existing_summary.summary_metadata.get("source"),
                        metadata=existing_summary.summary_metadata,
                        created_at=existing_summary.created_at,
                        updated_at=existing_summary.updated_at,
                    )

                return None

            except Exception as e:
                self.logger.error(
                    f"Error checking for existing {source} summary: {str(e)}",
                    exc_info=True,
                )
                # Return None to allow creating new summary
                return None

    def _build_error_detail(self, source: str, error: Exception) -> SummarizationError:
        """
        Build detailed error information from exception.

        Args:
            source: Source of the error ('transcript' or 'fhir_analysis')
            error: The exception that occurred

        Returns:
            SummarizationError with detailed information
        """
        error_type = type(error).__name__
        error_message = str(error)

        # Extract additional details based on error type
        details = None
        if hasattr(error, "detail"):
            details = str(error.detail)
        elif hasattr(error, "args") and error.args:
            details = ", ".join(str(arg) for arg in error.args)

        # Capture traceback for debugging
        tb = None
        try:
            tb = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        except Exception:
            pass

        self.logger.debug(
            f"Built error detail - source: {source}, type: {error_type}, message: {error_message}"
        )

        return SummarizationError(
            source=source,
            error_type=error_type,
            error_message=error_message,
            details=details,
            traceback=tb,
        )

    def _build_metrics(
        self,
        total_requested: int,
        success_count: int,
        error_count: int,
        execution_time: float,
        task_timings: dict,
        timeout_occurred: bool,
    ) -> SummarizationMetrics:
        """
        Build execution metrics.

        Args:
            total_requested: Total number of tasks requested
            success_count: Number of successful tasks
            error_count: Number of failed tasks
            execution_time: Total execution time in seconds
            task_timings: Dictionary of individual task timings
            timeout_occurred: Whether any timeout occurred

        Returns:
            SummarizationMetrics object
        """
        partial_success = success_count > 0 and error_count > 0

        metrics = SummarizationMetrics(
            total_requested=total_requested,
            success_count=success_count,
            error_count=error_count,
            execution_time_seconds=round(execution_time, 3),
            transcript_execution_time=task_timings.get("transcript"),
            fhir_execution_time=task_timings.get("fhir_analysis"),
            partial_success=partial_success,
            timeout_occurred=timeout_occurred,
        )

        self.logger.debug(
            f"Metrics calculated - "
            f"total: {total_requested}, "
            f"success: {success_count}, "
            f"errors: {error_count}, "
            f"execution_time: {execution_time:.2f}s, "
            f"partial_success: {partial_success}"
        )

        return metrics

    def _build_empty_response(
        self, message: str, start_time: datetime
    ) -> ComprehensiveSummarizationResponse:
        """
        Build empty response when no tasks are available.

        Args:
            message: Error message explaining why no tasks were executed
            start_time: When the operation started

        Returns:
            ComprehensiveSummarizationResponse with no summaries and an error
        """
        self.logger.warning(f"Empty response built - message: {message}")

        return ComprehensiveSummarizationResponse(
            success=False, message=None, summaries=[], fhir_summaries=[], error=message
        )
