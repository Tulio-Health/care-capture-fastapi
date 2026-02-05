from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.error_models import BusinessLogicError, ExternalServiceError
from ..common.logging import get_logger
from ..db.config.database import get_db
from ..models.comprehensive_summarization import (
    ComprehensiveSummarizationRequest,
    ComprehensiveSummarizationResponse,
)
from ..models.conversation_summaries import ConversationSummary
from ..models.fhir_analysis import FhirAnalysisRequest
from ..models.playground_summarization import (
    PlaygroundSummarizationRequest,
    PlaygroundSummarizationResponse,
)
from ..models.transcript_summarization import TranscriptSummarizationRequest
from ..services.summarization import (
    ComprehensiveSummarizationService,
    FhirAnalysisService,
    PlaygroundSummarizationService,
    TranscriptSummarizationService,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/care-capture", tags=["care-capture"])


@router.post(
    "/transcript-summarization",
    response_model=ConversationSummary,
    summary="Provider Visit Summarization",
    description="Summarize the given text with specified length constraints",
    responses={
        200: {
            "description": "Successful summarization",
            "content": {
                "application/json": {
                    "example": {
                        "summary": "This is a summary of the text...",
                        "original_length": 500,
                        "summary_length": 100,
                    }
                }
            },
        },
        400: {
            "description": "Invalid input parameters",
            "content": {"application/json": {"example": {"detail": "Text cannot be empty"}}},
        },
    },
)
async def transcript_summarize_text(
    request: TranscriptSummarizationRequest, db: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    """
    Summarize provider visit text and store in database.

    Args:
        request: Contains transcript_id and text to summarize
        db: Database session

    Returns:
        Created summary document

    Raises:
        HTTPException: If summarization fails
    """
    try:
        # Initialize service and delegate business logic
        service = TranscriptSummarizationService(db)
        return await service.summarize_transcript(request)

    except ValueError as e:
        # Raise a 400 error if input is invalid
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Raise a 500 error if any other exception occurs
        raise HTTPException(status_code=500, detail=f"Failed to process summary: {str(e)}")


@router.post(
    "/playground-summarization",
    response_model=PlaygroundSummarizationResponse,
    summary="Playground Text Summarization",
    description="Summarize plain text for testing purposes without database storage",
    responses={
        200: {
            "description": "Successful summarization",
            "content": {
                "application/json": {
                    "example": {
                        "request_id": "123e4567-e89b-12d3-a456-426614174000",
                        "provider_patient_discussion_summary_text": "Patient presents with headache lasting three days...",
                        "provider_patient_discussion_key_points": ["Headache for 3 days", "Taken pain relievers"],
                        "medications_prescribed_by_provider": [],
                        "medical_diagnoses_discussed": [],
                        "instructions_provided_by_provider": [],
                        "recommendations_provided_by_provider": [],
                    }
                }
            },
        },
        400: {
            "description": "Invalid input parameters",
            "content": {
                "application/json": {
                    "example": {
                        "error": True,
                        "error_type": "business_logic_error",
                        "message": "Invalid input provided",
                        "details": "Plain text cannot be empty or contain only whitespace",
                        "request_id": "a1b2c3d4",
                        "timestamp": "2024-10-04T12:00:00Z",
                        "path": "/care-capture/playground-summarization",
                        "method": "POST",
                    }
                }
            },
        },
        422: {
            "description": "Validation errors",
            "content": {
                "application/json": {
                    "example": {
                        "error": True,
                        "error_type": "validation_error",
                        "message": "Request validation failed",
                        "details": "Found 1 validation error(s)",
                        "validation_errors": [
                            {
                                "field": "plain_text",
                                "message": "field required",
                                "invalid_value": None,
                                "expected_type": "str",
                            }
                        ],
                        "request_id": "a1b2c3d4",
                        "timestamp": "2024-10-04T12:00:00Z",
                        "path": "/care-capture/playground-summarization",
                        "method": "POST",
                    }
                }
            },
        },
        503: {
            "description": "External service error",
            "content": {
                "application/json": {
                    "example": {
                        "error": True,
                        "error_type": "external_service_error",
                        "message": "External service error: OpenAI/LLM",
                        "details": "Error during text processing: API quota exceeded",
                        "request_id": "a1b2c3d4",
                        "timestamp": "2024-10-04T12:00:00Z",
                        "path": "/care-capture/playground-summarization",
                        "method": "POST",
                    }
                }
            },
        },
    },
)
async def playground_summarize_text(request: PlaygroundSummarizationRequest) -> PlaygroundSummarizationResponse:
    """
    Summarize plain text for testing purposes without database storage.

    Args:
        request: Contains plain_text, request_id, and language code

    Returns:
        Summarization results with request metadata

    Raises:
        HTTPException: If summarization fails
    """
    logger.info(f"Playground summarization request started - request_id: {request.request_id}")
    logger.debug(
        f"Request details - text_length: {len(request.plain_text) if request.plain_text else 0}, language: {request.language_code}"
    )

    try:
        # Initialize service and delegate business logic
        service = PlaygroundSummarizationService()
        return await service.summarize_plain_text(request)

    except (BusinessLogicError, ExternalServiceError, ValidationError):
        # Let these be handled by the exception handlers
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in playground summarization - request_id: {request.request_id}, error: {str(e)}",
            exc_info=True,
        )
        # This will be caught by the general exception handler
        raise


# @router.post("/users/{user_id}/health_insights",
#                 response_model=HealthInsightsResponse,
#                 summary="Health Insights Extraction",
#                 description="Extract key points from the given summaries",
#                 responses={
#                     200: {
#                         "description": "Successful key point extraction",
#                         "content": {
#                             "application/json": {
#                                 "example": {
#                                     "conditions": [
#                                         {
#                                             "name": "High blood pressure",
#                                             "details": "Patient has high blood pressure",
#                                             "date": "2023-01-01"
#                                         }
#                                     ],
#                                     "surgeriesAndProcedures": [
#                                         {
#                                             "name": "Surgery",
#                                             "details": "Surgery performed on patient",
#                                             "date": "2023-01-01"
#                                         }
#                                     ],
#                                     "medications": [
#                                         {
#                                             "name": "Medication",
#                                             "dosage": "10mg",
#                                             "frequency": "twice a day",
#                                             "date": "2023-01-01"
#                                         }
#                                     ],
#                                     "priorTesting": [
#                                         {
#                                             "name": "Test",
#                                             "result": "Positive",
#                                             "date": "2023-01-01"
#                                         }
#                                     ]
#                                 }
#                             }
#                         }
#                     },
#                     400: {
#                         "description": "Invalid input parameters",
#                         "content": {
#                             "application/json": {
#                                 "example": {"detail": "Summaries cannot be empty"}
#                             }
#                         }
#                     }
#                 })

# async def health_insights_extraction(
#     user_id: str,
#     db: AsyncSession = Depends(get_db),
# ):
#     try:
#         user_summaries = await ConversationSummariesRepository(db).get_by_user_id(user_id)
#         if not user_summaries:
#             raise HTTPException(status_code=404, detail="User not found")

#         user_summaries_obj = [HealthInsights.model_validate(summary, from_attributes=True) for summary in user_summaries]

#         clinical_keypoint_extraction_chain = TranscriptsSummarizationChain()
#         health_insights = clinical_keypoint_extraction_chain.extract(user_summaries_obj)
#         health_insights_dict = HealthInsightsResponse.model_validate_json(health_insights).model_dump()

#         await PatientHealthInsightsRepository(db).create(user_id=user_id, health_insights=health_insights_dict)
#         return health_insights_dict
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# ## TODO: Remove this endpoint after testing...
# @router.post("/users/health-insights/batch",
#              response_model=List[HealthInsightsResponse])
# async def batch_health_insights_extraction(
#         db: AsyncSession = Depends(get_db)):
#     try:
#         users = await UsersRepository(db).get_all()
#         if not users:
#             raise HTTPException(status_code=404, detail="No users found")

#         health_insights_list = []
#         for user in users:
#             try:
#                 insights = await health_insights_extraction(user_id=user.id, db=db)
#                 health_insights_list.append(insights)
#             except Exception as he:
#                 logger.error(f"Error extracting health insights for user {user.id}: {str(he)}")
#                 continue
#             except ValidationError as ve:
#                 raise HTTPException(status_code=422, detail=str(ve))
#             except ValueError as val_e:
#                 raise HTTPException(status_code=400, detail=str(val_e))
#         return health_insights_list

#     except HTTPException as he:
#         raise he
#     except Exception as e:
#         raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/fhir-analysis",
    response_model=ConversationSummary,
    summary="FHIR Resource Analysis",
    description="Analyze FHIR resources for a patient appointment and generate clinical insights, storing results in conversation_summaries",
    responses={
        200: {
            "description": "Successful FHIR analysis",
            "content": {
                "application/json": {
                    "example": {
                        "clinical_summary": "Patient has multiple chronic conditions...",
                        "key_insights": ["Insight 1", "Insight 2"],
                        "resource_counts": {"Condition": 10, "Observation": 5},
                    }
                }
            },
        },
        404: {
            "description": "Appointment or FHIR resources not found",
            "content": {"application/json": {"example": {"detail": "No FHIR resources found for user"}}},
        },
        500: {
            "description": "Internal server error",
            "content": {"application/json": {"example": {"detail": "Failed to analyze FHIR resources"}}},
        },
    },
)
async def analyze_fhir_resources(
    request: FhirAnalysisRequest, db: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    """
    Analyze FHIR resources for a patient appointment and generate clinical insights.

    Stores the analysis results in conversation_summaries table, following the same
    pattern as transcript_summarize_text API.

    Args:
        request: Contains appointment_id, user_id, and optional filters
        db: Database session

    Returns:
        ConversationSummary with clinical insights stored in the database

    Raises:
        HTTPException: If appointment not found or analysis fails
    """
    try:
        # Initialize service and delegate business logic
        service = FhirAnalysisService(db)
        return await service.analyze_fhir_resources(request)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ValueError as e:
        logger.error(f"Validation error in FHIR analysis: {str(e)}", exc_info=e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing FHIR resources: {str(e)}", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to analyze FHIR resources: {str(e)}")


@router.post(
    "/comprehensive-summary",
    response_model=ComprehensiveSummarizationResponse,
    summary="Comprehensive Summarization",
    description="Execute transcript summarization and FHIR analysis in parallel for a single appointment",
    responses={
        200: {
            "description": "Summarization completed (may include partial success)",
            "content": {
                "application/json": {
                    "example": {
                        "summaries": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "appointment_id": "123e4567-e89b-12d3-a456-426614174001",
                                "user_id": "123e4567-e89b-12d3-a456-426614174002",
                                "summary_text": "Patient presents with...",
                                "key_points": ["Point 1", "Point 2"],
                                "medications": [],
                                "diagnoses": [],
                                "instructions": [],
                                "recommendations": [],
                                "metadata": {
                                    "source": "transcript",
                                    "transcript_count": 2,
                                    "analysis_version": "1.0"
                                },
                                "created_at": "2024-01-01T00:00:00Z",
                                "updated_at": "2024-01-01T00:00:00Z",
                                "created_by": "123e4567-e89b-12d3-a456-426614174002",
                                "updated_by": "123e4567-e89b-12d3-a456-426614174002"
                            },
                            {
                                "id": "223e4567-e89b-12d3-a456-426614174000",
                                "appointment_id": "123e4567-e89b-12d3-a456-426614174001",
                                "user_id": "123e4567-e89b-12d3-a456-426614174002",
                                "summary_text": "FHIR analysis shows...",
                                "key_points": ["Insight 1", "Insight 2"],
                                "medications": [{"name": "Aspirin"}],
                                "diagnoses": ["Hypertension"],
                                "instructions": [],
                                "recommendations": [],
                                "metadata": {
                                    "source": "fhir_analysis",
                                    "total_resources": 50,
                                    "analysis_version": "1.0"
                                },
                                "created_at": "2024-01-01T00:00:00Z",
                                "updated_at": "2024-01-01T00:00:00Z",
                                "created_by": "123e4567-e89b-12d3-a456-426614174002",
                                "updated_by": "123e4567-e89b-12d3-a456-426614174002"
                            }
                        ],
                        "errors": [],
                        "metrics": {
                            "total_requested": 2,
                            "success_count": 2,
                            "error_count": 0,
                            "execution_time_seconds": 5.234,
                            "transcript_execution_time": 2.5,
                            "fhir_execution_time": 4.8,
                            "partial_success": False,
                            "timeout_occurred": False
                        }
                    }
                }
            },
        },
        400: {
            "description": "Invalid input parameters",
            "content": {
                "application/json": {
                    "example": {
                        "summaries": [],
                        "errors": [
                            {
                                "source": "transcript",
                                "error_type": "ValueError",
                                "error_message": "transcripts list cannot be empty",
                                "details": None,
                                "timestamp": "2024-01-01T00:00:00Z"
                            }
                        ],
                        "metrics": {
                            "total_requested": 1,
                            "success_count": 0,
                            "error_count": 1,
                            "execution_time_seconds": 0.05,
                            "partial_success": False,
                            "timeout_occurred": False
                        }
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "summaries": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "summary_text": "Transcript summary completed",
                                "metadata": {"source": "transcript"}
                            }
                        ],
                        "errors": [
                            {
                                "source": "fhir_analysis",
                                "error_type": "HTTPException",
                                "error_message": "No FHIR resources found",
                                "details": "Appointment has no EHR entity ID",
                                "timestamp": "2024-01-01T00:00:00Z"
                            }
                        ],
                        "metrics": {
                            "total_requested": 2,
                            "success_count": 1,
                            "error_count": 1,
                            "execution_time_seconds": 3.5,
                            "partial_success": True,
                            "timeout_occurred": False
                        }
                    }
                }
            },
        },
    },
)
async def comprehensive_summary(
    request: ComprehensiveSummarizationRequest, db: AsyncSession = Depends(get_db)
) -> ComprehensiveSummarizationResponse:
    """
    Execute comprehensive summarization (transcript + FHIR analysis) in parallel.
    
    This endpoint orchestrates multiple summarization operations concurrently for
    optimal performance. It supports partial success, meaning if one operation fails,
    the other can still succeed.
    
    **Features:**
    - Parallel execution using asyncio for faster response times
    - Partial success support (returns successful summaries even if some fail)
    - Detailed error tracking per source (transcript vs FHIR)
    - Execution metrics and timing for each operation
    - Configurable timeout to prevent long-running operations
    - Separate database transactions per operation
    
    **Request Parameters:**
    - `appointment_id`: Required. The appointment to summarize.
    - `user_id`: Required. The patient user ID.
    - `transcripts`: Optional. List of transcript objects. If provided, transcript summarization runs.
    - `include_fhir_analysis`: Optional. Default True. Whether to run FHIR analysis.
    - `resource_types`: Optional. Filter FHIR resources by type.
    - `analysis_focus`: Optional. Focus area for FHIR analysis.
    - `timeout_seconds`: Optional. Default 120. Maximum execution time (10-300 seconds).
    
    **Response Structure:**
    - `summaries`: List of ConversationSummary objects. Each has `metadata.source` field:
      - `"transcript"`: From transcript summarization
      - `"fhir_analysis"`: From FHIR analysis
    - `errors`: List of errors for failed operations with detailed information
    - `metrics`: Execution statistics including timing and success rates
    
    **Success Scenarios:**
    - **Complete Success**: All requested operations succeeded (errors list is empty)
    - **Partial Success**: Some succeeded, some failed (both summaries and errors present)
    - **Complete Failure**: All operations failed (summaries list is empty)
    
    **HTTP Status:** Always returns 200 OK, even for partial or complete failure.
    Check the `metrics` and `errors` fields to determine actual success status.
    
    Args:
        request: Comprehensive summarization request with all parameters
        db: Database session (injected)
    
    Returns:
        ComprehensiveSummarizationResponse with summaries, errors, and metrics
    
    Raises:
        HTTPException: Only for request validation errors (400)
    """
    logger.info(
        f"Comprehensive summary request received - "
        f"appointment_id: {request.appointment_id}, "
        f"user_id: {request.user_id}, "
        f"has_transcripts: {request.has_transcript_data()}, "
        f"include_fhir: {request.has_fhir_data_requested()}"
    )

    try:
        # Initialize service and delegate business logic
        service = ComprehensiveSummarizationService(db)
        response = await service.execute_parallel_summarization(request)

        # Log summary of results
        logger.info(
            f"Comprehensive summary completed - "
            f"appointment_id: {request.appointment_id}, "
            f"success: {response.metrics.success_count}/{response.metrics.total_requested}, "
            f"errors: {response.metrics.error_count}, "
            f"partial_success: {response.metrics.partial_success}, "
            f"execution_time: {response.metrics.execution_time_seconds:.2f}s"
        )

        # Log detailed results for each source
        if response.summaries:
            for summary in response.summaries:
                source = summary.metadata.get("source", "unknown") if summary.metadata else "unknown"
                logger.debug(
                    f"Summary created - source: {source}, summary_id: {summary.id}"
                )

        if response.errors:
            for error in response.errors:
                logger.warning(
                    f"Summarization error - "
                    f"source: {error.source}, "
                    f"type: {error.error_type}, "
                    f"message: {error.error_message}"
                )

        return response

    except ValidationError as e:
        logger.error(
            f"Validation error in comprehensive summary - "
            f"appointment_id: {request.appointment_id}, "
            f"error: {str(e)}",
            exc_info=True
        )
        raise HTTPException(status_code=400, detail=f"Request validation failed: {str(e)}")
    
    except Exception as e:
        logger.error(
            f"Unexpected error in comprehensive summary - "
            f"appointment_id: {request.appointment_id}, "
            f"error: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to execute comprehensive summarization: {str(e)}"
        )

