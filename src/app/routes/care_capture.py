from typing import List
from fastapi import APIRouter, HTTPException , Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..chains.provider_visit_summarization import ProvidervisitSummarizationChain
from ..models.provider_visit_summarization import ProviderVisitSummarizationRequest, ProviderVisitSummarizationResponse
from ..models.health_insights_extraction import HealthInsightsRequest, HealthInsightsResponse , HealthInsights
from ..chains.health_insights_extraction import HeathInsightsExtractionChain
from ..db.config.database import get_db
from ..db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from ..db.objects.repositories.patient_health_insights import PatientHealthInsightsRepository
from ..db.objects.repositories.users import UsersRepository
from ..common.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/care-capture",
    tags=["care-capture"]
)

@router.post("/provider_visit_summarization",
    response_model=ProviderVisitSummarizationResponse,
    
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
                        "summary_length": 100
                    }
                }
            }
        },
        400: {
            "description": "Invalid input parameters",
            "content": {
                "application/json": {
                    "example": {"detail": "Text cannot be empty"}
                }
            }
        }
    }
)

async def provider_visit_summarize_text(
    request: ProviderVisitSummarizationRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
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
        # Check if the input text is empty
        if not request.text.strip():
            raise ValueError("Text cannot be empty")
            
        # Initialize the repository for conversation summaries
        conversation_summaries_repository = ConversationSummariesRepository(db)
        # Create an instance of the summarization chain
        summarization_chain = ProvidervisitSummarizationChain()
        
        # Summarize the provided text
        summary = summarization_chain.summarize(request.text)
        # Validate the summary model
        summary_model = ProviderVisitSummarizationResponse.model_validate_json(summary)
        
        # Prepare the summary dictionary for database insertion
        summary_dict = summary_model.model_dump()
        summary_dict["transcript_id"] = request.transcript_id
        summary_dict["user_id"] = request.user_id
        summary_dict["created_by"] = request.user_id
        summary_dict["updated_by"] = request.user_id


                
        # Create a new summary entry in the database
        return await conversation_summaries_repository.create(conversation_summary=summary_dict)
    
    except ValueError as e:
        # Raise a 400 error if input is invalid
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Raise a 500 error if any other exception occurs
        raise HTTPException(status_code=500, detail=f"Failed to process summary: {str(e)}")
    
@router.post("/users/{user_id}/health_insights",
                response_model=HealthInsightsResponse,
                summary="Health Insights Extraction",
                description="Extract key points from the given summaries",
                responses={
                    200: {
                        "description": "Successful key point extraction",
                        "content": {
                            "application/json": {
                                "example": {
                                    "conditions": [
                                        {
                                            "name": "High blood pressure",
                                            "details": "Patient has high blood pressure",
                                            "date": "2023-01-01"
                                        }
                                    ],
                                    "surgeriesAndProcedures": [
                                        {
                                            "name": "Surgery",
                                            "details": "Surgery performed on patient",
                                            "date": "2023-01-01"
                                        }
                                    ],
                                    "medications": [
                                        {
                                            "name": "Medication",
                                            "dosage": "10mg",
                                            "frequency": "twice a day",
                                            "date": "2023-01-01"
                                        }
                                    ],
                                    "priorTesting": [
                                        {
                                            "name": "Test",
                                            "result": "Positive",
                                            "date": "2023-01-01"
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    400: {
                        "description": "Invalid input parameters",
                        "content": {
                            "application/json": {
                                "example": {"detail": "Summaries cannot be empty"}
                            }
                        }
                    }
                })

async def health_insights_extraction(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        user_summaries = await ConversationSummariesRepository(db).get_by_user_id(user_id)
        if not user_summaries:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_summaries_obj = [HealthInsights.model_validate(summary, from_attributes=True) for summary in user_summaries]
      
        clinical_keypoint_extraction_chain = HeathInsightsExtractionChain()
        health_insights = clinical_keypoint_extraction_chain.extract(user_summaries_obj)                
        health_insights_dict = HealthInsightsResponse.model_validate_json(health_insights).model_dump()
        
        await PatientHealthInsightsRepository(db).create(user_id=user_id, health_insights=health_insights_dict)
        return health_insights_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/health-insights/batch",
             response_model=List[HealthInsightsResponse])
async def batch_health_insights_extraction(
        db: AsyncSession = Depends(get_db)):
    try:
        users = await UsersRepository(db).get_all()
        if not users:
            raise HTTPException(status_code=404, detail="No users found")
        
        health_insights_list = []
        for user in users:
            try:
                insights = await health_insights_extraction(user_id=user.id, db=db)
                health_insights_list.append(insights)
            except Exception as he:
                logger.error(f"Error extracting health insights for user {user.id}: {str(he)}")
                continue
            except ValidationError as ve:
                raise HTTPException(status_code=422, detail=str(ve))
            except ValueError as val_e:
                raise HTTPException(status_code=400, detail=str(val_e))  
        return health_insights_list
                
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")