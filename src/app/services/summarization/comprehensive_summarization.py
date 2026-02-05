"""Comprehensive Summarization Service - Orchestrates multiple summarization services in parallel."""

import asyncio
import traceback
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.common.logging import get_logger
from src.app.models.comprehensive_summarization import (
    ComprehensiveSummarizationRequest,
    ComprehensiveSummarizationResponse,
    SummarizationError,
    SummarizationMetrics,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.models.fhir_analysis import FhirAnalysisRequest
from src.app.models.transcript_summarization import TranscriptSummarizationRequest

from .fhir_analysis import FhirAnalysisService
from .transcript_summarization import TranscriptSummarizationService

logger = get_logger(__name__)


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
            db: Database session for repository operations
        """
        self.db = db
        self.transcript_service = TranscriptSummarizationService(db)
        self.fhir_service = FhirAnalysisService(db)
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

        # Build list of tasks to execute
        tasks, task_sources = self._build_task_list(request)

        if not tasks:
            self.logger.warning(
                f"No tasks to execute - "
                f"appointment_id: {request.appointment_id}"
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
        summaries, errors, task_timings = self._process_results(results, task_sources)

        # Calculate metrics
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        metrics = self._build_metrics(
            total_requested=len(tasks),
            success_count=len(summaries),
            error_count=len(errors),
            execution_time=execution_time,
            task_timings=task_timings,
            timeout_occurred=any(
                isinstance(r, asyncio.TimeoutError) for r in results
            ),
        )

        self.logger.info(
            f"Comprehensive summarization completed - "
            f"appointment_id: {request.appointment_id}, "
            f"success: {metrics.success_count}/{metrics.total_requested}, "
            f"execution_time: {metrics.execution_time_seconds:.2f}s, "
            f"partial_success: {metrics.partial_success}"
        )

        return ComprehensiveSummarizationResponse(
            summaries=summaries, errors=errors, metrics=metrics
        )

    def _build_task_list(
        self, request: ComprehensiveSummarizationRequest
    ) -> Tuple[List, List[str]]:
        """
        Build list of tasks to execute based on available data.
        
        Args:
            request: Comprehensive summarization request
        
        Returns:
            Tuple of (tasks list, task source names)
        """
        tasks = []
        task_sources = []

        # Add transcript summarization if data available
        if request.has_transcript_data():
            self.logger.debug(
                f"Adding transcript summarization task - "
                f"transcript_count: {len(request.transcripts)}, "
                f"appointment_id: {request.appointment_id}"
            )
            tasks.append(self._run_transcript_summarization(request))
            task_sources.append("transcript")

        # Add FHIR analysis if requested
        if request.has_fhir_data_requested():
            self.logger.debug(
                f"Adding FHIR analysis task - "
                f"resource_types: {request.resource_types}, "
                f"analysis_focus: {request.analysis_focus}, "
                f"appointment_id: {request.appointment_id}"
            )
            tasks.append(self._run_fhir_analysis(request))
            task_sources.append("fhir_analysis")

        self.logger.debug(
            f"Task list built - "
            f"task_count: {len(tasks)}, sources: {task_sources}, "
            f"appointment_id: {request.appointment_id}"
        )

        return tasks, task_sources

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
            f"Starting parallel execution - "
            f"task_count: {len(tasks)}, timeout: {timeout_seconds}s"
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
                f"Parallel execution timed out after {timeout_seconds}s - "
                f"tasks: {task_sources}"
            )
            # Return timeout errors for all tasks
            return [asyncio.TimeoutError(f"Operation timed out after {timeout_seconds}s")] * len(
                tasks
            )

    def _process_results(
        self, results: List, task_sources: List[str]
    ) -> Tuple[List[ConversationSummary], List[SummarizationError], dict]:
        """
        Process parallel execution results.
        
        Separates successful summaries from errors and tracks timing.
        
        Args:
            results: List of results from asyncio.gather()
            task_sources: List of source names for each task
        
        Returns:
            Tuple of (summaries, errors, task_timings)
        """
        summaries = []
        errors = []
        task_timings = {}

        self.logger.debug(
            f"Processing {len(results)} results from parallel execution"
        )

        for idx, result in enumerate(results):
            source = task_sources[idx]
            
            if isinstance(result, Exception):
                # Handle error
                error = self._build_error_detail(source, result)
                errors.append(error)
                
                self.logger.error(
                    f"Summarization failed - "
                    f"source: {source}, "
                    f"error_type: {error.error_type}, "
                    f"error: {error.error_message}"
                )
                
            elif result is not None:
                # Handle success
                summaries.append(result)
                
                # Extract timing from metadata if available
                if hasattr(result, "metadata") and result.metadata:
                    timing_key = f"{source}_execution_time"
                    if timing_key in result.metadata:
                        task_timings[source] = result.metadata[timing_key]
                
                self.logger.info(
                    f"Summarization succeeded - "
                    f"source: {source}, "
                    f"summary_id: {result.id if hasattr(result, 'id') else 'unknown'}"
                )
            else:
                # Handle None result (shouldn't happen, but defensive)
                self.logger.warning(
                    f"Summarization returned None - source: {source}"
                )
                error = SummarizationError(
                    source=source,
                    error_type="NullResult",
                    error_message="Summarization returned no result",
                    details="Service returned None instead of ConversationSummary",
                )
                errors.append(error)

        self.logger.debug(
            f"Results processed - "
            f"successes: {len(summaries)}, errors: {len(errors)}"
        )

        return summaries, errors, task_timings

    async def _run_transcript_summarization(
        self, request: ComprehensiveSummarizationRequest
    ) -> Optional[ConversationSummary]:
        """
        Execute transcript summarization.
        
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
            f"transcript_count: {len(request.transcripts)}"
        )

        try:
            # Build transcript-specific request
            transcript_req = TranscriptSummarizationRequest(
                appointment_id=request.appointment_id,
                transcripts=request.transcripts,
                user_id=request.user_id,
            )

            # Execute summarization
            result = await self.transcript_service.summarize_transcript(transcript_req)

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
        Execute FHIR analysis.
        
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

        try:
            # Build FHIR-specific request
            fhir_req = FhirAnalysisRequest(
                appointment_id=request.appointment_id,
                user_id=request.user_id,
                resource_types=request.resource_types,
                analysis_focus=request.analysis_focus,
            )

            # Execute analysis
            result = await self.fhir_service.analyze_fhir_resources(fhir_req)

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

    def _build_error_detail(
        self, source: str, error: Exception
    ) -> SummarizationError:
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
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        except Exception:
            pass

        self.logger.debug(
            f"Built error detail - "
            f"source: {source}, type: {error_type}, message: {error_message}"
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
        execution_time = (datetime.utcnow() - start_time).total_seconds()

        error = SummarizationError(
            source="system",
            error_type="NoDataAvailable",
            error_message=message,
            details="Neither transcript data nor FHIR analysis was requested/available",
        )

        metrics = SummarizationMetrics(
            total_requested=0,
            success_count=0,
            error_count=1,
            execution_time_seconds=round(execution_time, 3),
            partial_success=False,
            timeout_occurred=False,
        )

        self.logger.warning(f"Empty response built - message: {message}")

        return ComprehensiveSummarizationResponse(
            summaries=[], errors=[error], metrics=metrics
        )
