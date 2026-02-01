from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.fhir_analysis.chain import FhirAnalysisChain
from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain

from ..common.error_models import BusinessLogicError, ExternalServiceError
from ..common.logging import get_logger
from ..db.config.database import get_db
from ..db.models.appointments import Appointment
from ..db.models.ref_cms_provider_data import RefCmsProviderData
from ..db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from ..db.objects.repositories.fhir_resources import FhirResourcesRepository
from ..db.objects.repositories.patient_health_insights import (
    PatientHealthInsightsRepository,
)
from ..db.objects.repositories.users import UsersRepository
from ..models.conversation_summaries import ConversationSummary
from ..models.fhir_analysis import FhirAnalysisRequest, FhirAnalysisResponse
from ..models.health_insights_extraction import HealthInsights, HealthInsightsResponse
from ..models.playground_summarization import (
    PlaygroundSummarizationRequest,
    PlaygroundSummarizationResponse,
)
from ..models.transcript_summarization import (
    TranscriptSummarizationRequest,
    TranscriptSummarizationResponse,
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
        # Initialize the repository for conversation summaries
        conversation_summaries_repository = ConversationSummariesRepository(db)
        # Create an instance of the summarization chain
        summarization_chain = TranscriptSummarizationChain()
        # Summarize the provided text
        summary = summarization_chain.summarize(request)
        # Validate the summary model
        summary_model = TranscriptSummarizationResponse.model_validate_json(summary.model_dump_json())

        # Prepare the summary data for database insertion
        summary_data = {
            "summary_text": summary_model.provider_patient_discussion_summary_text,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": summary_model.provider_patient_discussion_key_points,
            "medications": summary_model.medications_prescribed_by_provider,
            "diagnoses": summary_model.medical_diagnoses_discussed,
            "instructions": summary_model.instructions_provided_by_provider,
            "recommendations": summary_model.recommendations_provided_by_provider,
        }

        # Create a new summary entry in the database
        db_summary = await conversation_summaries_repository.upsert(
            appointment_id=request.appointment_id, summary_data=summary_data
        )

        # Return the response using the proper Pydantic model
        return ConversationSummary.model_validate(db_summary)

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
        # Validate input
        if not request.plain_text or not request.plain_text.strip():
            logger.warning(f"Empty or whitespace-only text provided - request_id: {request.request_id}")
            raise BusinessLogicError(
                message="Invalid input provided", details="Plain text cannot be empty or contain only whitespace"
            )

        text_length = len(request.plain_text.strip())
        if text_length < 10:
            logger.warning(
                f"Text too short for summarization - request_id: {request.request_id}, length: {text_length}"
            )
            raise BusinessLogicError(
                message="Text too short for summarization", details=f"Minimum 10 characters required, got {text_length}"
            )

        if text_length > 50000:  # Example limit
            logger.warning(f"Text too long for summarization - request_id: {request.request_id}, length: {text_length}")
            raise BusinessLogicError(
                message="Text too long for summarization",
                details=f"Maximum 50,000 characters allowed, got {text_length}",
            )

        logger.info(f"Processing text with {text_length} characters - request_id: {request.request_id}")

        # Create an instance of the summarization chain
        logger.debug(f"Initializing TranscriptSummarizationChain - request_id: {request.request_id}")
        try:
            summarization_chain = TranscriptSummarizationChain()
        except Exception as e:
            logger.error(
                f"Failed to initialize summarization chain - request_id: {request.request_id}, error: {str(e)}"
            )
            raise ExternalServiceError(
                service="TranscriptSummarizationChain",
                message="Failed to initialize summarization service",
                details=str(e),
            )

        # Summarize the provided plain text directly
        logger.info(f"Starting summarization process - request_id: {request.request_id}")
        try:
            summary = summarization_chain.summarize(request.plain_text)
            logger.debug(f"Raw summary generated - request_id: {request.request_id}")
        except Exception as e:
            logger.error(f"Summarization process failed - request_id: {request.request_id}, error: {str(e)}")
            raise ExternalServiceError(
                service="OpenAI/LLM",
                message="Summarization process failed",
                details=f"Error during text processing: {str(e)}",
            )

        # Validate the summary model
        logger.debug(f"Validating summary model - request_id: {request.request_id}")
        try:
            summary_model = TranscriptSummarizationResponse.model_validate_json(summary.model_dump_json())
        except ValidationError as e:
            logger.error(f"Summary model validation failed - request_id: {request.request_id}, error: {str(e)}")
            # Let ValidationError bubble up to be handled by the validation error handler
            raise

        # Log summary statistics
        summary_text_length = (
            len(summary_model.provider_patient_discussion_summary_text)
            if summary_model.provider_patient_discussion_summary_text
            else 0
        )
        key_points_count = (
            len(summary_model.provider_patient_discussion_key_points)
            if summary_model.provider_patient_discussion_key_points
            else 0
        )
        medications_count = (
            len(summary_model.medications_prescribed_by_provider)
            if summary_model.medications_prescribed_by_provider
            else 0
        )

        logger.info(
            f"Summary generated successfully - request_id: {request.request_id}, "
            f"summary_length: {summary_text_length}, key_points: {key_points_count}, "
            f"medications: {medications_count}"
        )

        # Create the data object first
        data = TranscriptSummarizationResponse(
            provider_patient_discussion_summary_text=summary_model.provider_patient_discussion_summary_text,
            provider_patient_discussion_key_points=summary_model.provider_patient_discussion_key_points,
            medications_prescribed_by_provider=summary_model.medications_prescribed_by_provider,
            medical_diagnoses_discussed=summary_model.medical_diagnoses_discussed,
            instructions_provided_by_provider=summary_model.instructions_provided_by_provider,
            recommendations_provided_by_provider=summary_model.recommendations_provided_by_provider,
        )

        # Return the response using the playground response model
        response = PlaygroundSummarizationResponse(request_id=request.request_id, data=data)

        logger.info(f"Playground summarization completed successfully - request_id: {request.request_id}")
        return response

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
    response_model=FhirAnalysisResponse,
    summary="FHIR Resource Analysis",
    description="Analyze FHIR resources for a patient appointment and generate clinical insights",
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
) -> FhirAnalysisResponse:
    """
    Analyze FHIR resources for a patient appointment and generate clinical insights.

    Args:
        request: Contains appointment_id, user_id, and optional filters
        db: Database session

    Returns:
        FhirAnalysisResponse with clinical insights and recommendations

    Raises:
        HTTPException: If appointment not found or analysis fails
    """
    try:
        # Initialize repositories
        fhir_repo = FhirResourcesRepository(db)
        summaries_repo = ConversationSummariesRepository(db)

        # 1. Fetch appointment details
        appointment_stmt = select(Appointment).where(Appointment.id == request.appointment_id)
        appointment_result = await db.execute(appointment_stmt)
        appointment = appointment_result.scalar_one_or_none()

        if not appointment:
            raise HTTPException(status_code=404, detail=f"Appointment {request.appointment_id} not found")

        # Fetch provider details if available
        provider_name = "N/A"
        if appointment.provider_id:
            provider_stmt = select(RefCmsProviderData).where(RefCmsProviderData.id == appointment.provider_id)
            provider_result = await db.execute(provider_stmt)
            provider = provider_result.scalar_one_or_none()
            if provider:
                provider_name = f"{provider.provider_first_name} {provider.provider_last_name}"

        # 2. Fetch FHIR resources for this specific appointment/encounter
        # This includes the Encounter itself AND all resources that reference it
        if not appointment.ehr_entity_id:
            raise HTTPException(
                status_code=400,
                detail=f"Appointment {request.appointment_id} has no EHR entity ID - cannot fetch FHIR resources",
            )

        # Use the comprehensive method that fetches:
        # 1. The Encounter resource itself
        # 2. All clinical resources (Observations, Conditions, etc.) that reference this encounter
        fhir_resources = await fhir_repo.get_encounter_with_clinical_data(
            user_id=str(request.user_id), encounter_id=appointment.ehr_entity_id, resource_types=request.resource_types
        )

        if not fhir_resources:
            raise HTTPException(
                status_code=404,
                detail=f"No FHIR resources found for appointment {request.appointment_id} (encounter: {appointment.ehr_entity_id})",
            )

        # 3. Get resource counts for this encounter
        resource_counts = await fhir_repo.get_resource_counts_by_encounter(
            user_id=str(request.user_id), encounter_id=appointment.ehr_entity_id
        )

        # 4. Build FHIR summary by grouping resources by type
        fhir_summary_by_type = {}
        for resource in fhir_resources:
            resource_type = resource.resource_type  # Now a string, not enum
            if resource_type not in fhir_summary_by_type:
                fhir_summary_by_type[resource_type] = []
            fhir_summary_by_type[resource_type].append(resource.data)

        # Format FHIR summary for AI prompt
        fhir_summary_text = ""
        for resource_type, resources in fhir_summary_by_type.items():
            fhir_summary_text += f"\n**{resource_type}** ({len(resources)} records):\n"
            # Limit to first 10 records per type to avoid context overflow
            for idx, resource_data in enumerate(resources[:10]):
                # Extract key fields based on resource type
                if resource_type == "Condition":
                    code_text = resource_data.get("codeText", "N/A")
                    category = (
                        resource_data.get("categoryText", ["N/A"])[0] if resource_data.get("categoryText") else "N/A"
                    )
                    fhir_summary_text += f"  {idx + 1}. {code_text} ({category})\n"
                elif resource_type == "Observation":
                    code_text = resource_data.get("codeText", "N/A")
                    value = resource_data.get("valueQuantity", {}).get("value", "N/A")
                    unit = resource_data.get("valueQuantity", {}).get("unit", "")
                    fhir_summary_text += f"  {idx + 1}. {code_text}: {value} {unit}\n"
                elif resource_type == "MedicationRequest":
                    medication = resource_data.get("medicationCodeText", "N/A")
                    status = resource_data.get("status", "N/A")
                    fhir_summary_text += f"  {idx + 1}. {medication} (Status: {status})\n"
                else:
                    # Generic summary for other types
                    metadata = resource_data.get("metadata", {})
                    fhir_summary_text += f"  {idx + 1}. {metadata.get('resourceType', resource_type)}\n"

            if len(resources) > 10:
                fhir_summary_text += f"  ... and {len(resources) - 10} more records\n"

        # 5. Build appointment context
        appointment_context = {
            "appointment_date": appointment.appointment_date.isoformat() if appointment.appointment_date else "N/A",
            "purpose": appointment.purpose or "N/A",
            "provider_name": provider_name,
        }

        # 6. Run AI analysis
        analysis_chain = FhirAnalysisChain()
        analysis_result = analysis_chain.analyze(
            appointment_context=appointment_context, fhir_summary=fhir_summary_text, resource_counts=resource_counts
        )

        # 7. Extract structured data for database storage
        conditions_list = [
            resource.data.get("codeText", "Unknown")
            for resource in fhir_resources
            if resource.resource_type == "Condition"  # Now a string, not enum
        ][:20]  # Limit to first 20

        medications_list = [
            {"name": resource.data.get("medicationCodeText", "Unknown")}
            for resource in fhir_resources
            if resource.resource_type == "MedicationRequest"  # Now a string, not enum
        ][:20]  # Limit to first 20

        # 8. Store analysis in conversation_summaries with metadata
        summary_data = {
            "appointment_id": request.appointment_id,
            "user_id": request.user_id,
            "summary_text": analysis_result.clinical_summary,
            "key_points": analysis_result.key_insights,
            "diagnoses": conditions_list,
            "medications": medications_list,
            "recommendations": analysis_result.recommendations,
            "created_by": request.user_id,
            "updated_by": request.user_id,
        }

        db_summary = await summaries_repo.create_with_metadata(summary_data=summary_data, source="fhir_analysis")

        # 9. Add metadata to response
        analysis_result.resource_counts = resource_counts
        analysis_result.metadata = {
            "source": "fhir_analysis",
            "summary_id": str(db_summary.id),
            "total_resources": len(fhir_resources),
            "appointment_id": str(request.appointment_id),
            "analysis_focus": request.analysis_focus,
        }

        return analysis_result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ValueError as e:
        logger.error(f"Validation error in FHIR analysis: {str(e)}", exc_info=e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing FHIR resources: {str(e)}", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to analyze FHIR resources: {str(e)}")
