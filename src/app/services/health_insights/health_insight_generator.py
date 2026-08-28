import logging
from typing import Dict, Any, List, Optional, Union
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.app.db.objects.entities.patient_health_insights import PatientHealthInsights
from src.app.db.objects.repositories.patient_health_insights import PatientHealthInsightsRepository
from ...db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from ...db.objects.entities.conversation_summaries import ConversationSummaries
from ...common.scheduler.job_execution_db_log import JobExecutionLogger
from ...models.conversation_summaries import ConversationSummary
from ...constants.scheduler import HEALTH_INSIGHT_JOB_ID
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID
from ...chains.health_insights.chain import GenerateHealthInsightsChain
from ...models.health_insights_extraction import HealthInsightsResponse

logger = logging.getLogger(__name__)


def _diagnosis_to_text(diagnosis: Union[str, Dict[str, Any]]) -> str:
    """Render a diagnosis entry as text, handling both the legacy flat-string shape
    and the newer {official_diagnosis, lay_explanation} shape."""
    if isinstance(diagnosis, dict):
        official = diagnosis.get("official_diagnosis") or diagnosis.get("diagnosis") or ""
        lay = diagnosis.get("lay_explanation") or ""
        return f"{official} ({lay})" if lay else official
    return str(diagnosis)


class SimplifiedConversationSummary(BaseModel):
    """Simplified model containing only essential fields from ConversationSummary."""
    summary_text: str = Field(..., description="The main summary text of the conversation")
    key_points: Optional[List[str]] = Field(None, description="Key points extracted from the conversation")
    medications: Optional[List[Dict[str, Any]]] = Field(None, description="Medications mentioned in the conversation")
    diagnoses: Optional[List[Union[str, Dict[str, Any]]]] = Field(None, description="Diagnoses discussed in the conversation")
    instructions: Optional[List[str]] = Field(None, description="Instructions provided during the conversation")
    recommendations: Optional[List[Dict[str, Any]]] = Field(None, description="Recommendations made during the conversation")

class GroupedConversationSummaries(BaseModel):
    """Model for grouping conversation summaries by user ID."""
    user_id: UUID
    summaries: List[SimplifiedConversationSummary]

class HealthInsightGenerator:
    """Class responsible for generating health insights for all the patients."""
    
    def __init__(self, session: AsyncSession):
        """Initialize the health insight generator."""
        self.logger = logger
        self.session = session
        self.conversation_repo = ConversationSummariesRepository(session)
        self.job_logger = JobExecutionLogger(session)
        self.health_insights_chain = GenerateHealthInsightsChain()
        self.health_insights_repo = PatientHealthInsightsRepository(session)
    
    async def _fetch_patient_visit_summaries(self, last_job_exec_time: datetime) -> Dict[UUID, GroupedConversationSummaries]:
        """
        Fetch visit summaries for all patients from conversation_summaries table
        that were created after the job start time and group them by user_id.
        
        Args:
            job_start_time (datetime): The timestamp when the job started
            
        Returns:
            Dict[UUID, GroupedConversationSummaries]: Dictionary mapping user IDs to their grouped summaries
        """
        try:
            self.logger.info(f"Starting to fetch patient visit summaries created after {last_job_exec_time}...")
            
            # Fetch conversation summaries created after job start time
            query = select(ConversationSummaries).where(
                ConversationSummaries.created_at >= last_job_exec_time
            ).order_by(ConversationSummaries.created_at.desc())
                        
            self.logger.debug(f"Executing query: {query}")
            conversation_summaries_result = await self.session.execute(query)
            
            conversation_summaries = conversation_summaries_result.scalars().all()
            
            self.logger.info(f"Found {len(conversation_summaries)} summaries in database")
            
            # Group summaries by user_id
            grouped_summaries_by_user_id: Dict[UUID, GroupedConversationSummaries] = {}
            
            for summary in conversation_summaries:
                try:
                    summary_model = ConversationSummary.model_validate(summary)
                    
                    # Create simplified summary
                    simplified_conversion_summary = SimplifiedConversationSummary(
                        summary_text=summary_model.summary_text,
                        key_points=summary_model.key_points,
                        medications=summary_model.medications,
                        diagnoses=summary_model.diagnoses,
                        instructions=summary_model.instructions,
                        recommendations=summary_model.recommendations
                    )
                    
                    # Initialize group if it doesn't exist
                    if summary_model.user_id not in grouped_summaries_by_user_id:
                        grouped_summaries_by_user_id[summary_model.user_id] = GroupedConversationSummaries(
                            user_id=summary_model.user_id,
                            summaries=[]
                        )
                    
                    # Add simplified summary to the appropriate group
                    grouped_summaries_by_user_id[summary_model.user_id].summaries.append(simplified_conversion_summary)
                    
                except Exception as e:
                    self.logger.error(f"Error converting summary {summary.id} to Pydantic model: {str(e)}")
                    continue
            
            self.logger.info(f"Successfully grouped {len(grouped_summaries_by_user_id)} users' summaries")
            return grouped_summaries_by_user_id
            
        except Exception as e:
            self.logger.error(f"Error fetching patient visit summaries: {str(e)}", exc_info=e)
            raise
    
    async def _generate_health_insights(self, grouped_summaries: Dict[UUID, GroupedConversationSummaries]) -> Dict[UUID, HealthInsightsResponse]:
        """
        Generate health insights for each user based on their conversation summaries.
        
        Args:
            grouped_summaries (Dict[UUID, GroupedConversationSummaries]): Dictionary of user IDs to their grouped summaries
            
        Returns:
            Dict[UUID, HealthInsightsResponse]: Dictionary mapping user IDs to their generated health insights
        """
        try:
            self.logger.info("Starting health insights generation for all users...")
            health_insights_by_user: Dict[UUID, HealthInsightsResponse] = {}
            
            for user_id, user_summaries in grouped_summaries.items():
                try:
                    self.logger.info(f"Generating health insights for user {user_id}")
                    
                    # Prepare the context for LLM by combining all summaries
                    combined_text = "\n\n".join([
                        f"Summary {i+1}:\n{summary.summary_text}\n"
                        f"Key Points: {', '.join(summary.key_points or [])}\n"
                        f"Medications: {', '.join(str(m) for m in summary.medications or [])}\n"
                        f"Diagnoses: {', '.join(_diagnosis_to_text(d) for d in summary.diagnoses or [])}\n"
                        f"Instructions: {', '.join(summary.instructions or [])}\n"
                        f"Recommendations: {', '.join(str(r) for r in summary.recommendations or [])}"
                        for i, summary in enumerate(user_summaries.summaries)
                    ])
                    
                    # Generate health insights using the chain
                    health_insights = self.health_insights_chain.generate_health_insights(combined_text)                                   
                    health_insights_by_user[user_id] = jsonable_encoder(health_insights)
                    self.logger.info(f"Successfully generated health insights for user {user_id}")
                    
                except Exception as e:
                    self.logger.error(f"Error generating health insights for user {user_id}: {str(e)}", exc_info=e)
                    continue
            
            self.logger.info(f"Completed health insights generation for {len(health_insights_by_user)} users")
            return health_insights_by_user
            
        except Exception as e:
            self.logger.error(f"Error in health insights generation: {str(e)}", exc_info=e)
            raise

    async def _save_health_insights(self, health_insights: Dict[UUID, HealthInsightsResponse]) -> None:
        """
        Save the generated health insights to the database.
        
        Args:
            health_insights (Dict[UUID, HealthInsightsResponse]): Dictionary of user IDs to their health insights
        """
        try:
            self.logger.info("Starting to save health insights to database...")
            
            # TODO: Implement the actual database save logic
            # This is a placeholder for the actual database operations
            # You should replace this with your actual database operations
            
            for user_id, insights in health_insights.items():
                try:
                    self.logger.info(f"Saving health insights for user {user_id}")
                    
                    # TODO: Add your database save logic here
                    # Example:
                    await self.health_insights_repo.create(
                        user_id=user_id,
                        health_insights=insights,
                        month=datetime.now().month,
                        year=datetime.now().year,
                    )
                    
                    self.logger.info(f"Successfully saved health insights for user {user_id}")
                    
                except Exception as e:
                    self.logger.error(f"Error saving health insights for user {user_id}: {str(e)}", exc_info=e)
                    continue
            
            self.logger.info(f"Completed saving health insights for {len(health_insights)} users")
            
        except Exception as e:
            self.logger.error(f"Error saving health insights: {str(e)}", exc_info=e)
            raise

    async def _fetch_patient_health_insights(self, user_ids: list[UUID] = None) -> Optional[PatientHealthInsights]:
        try:
            self.logger.info(f"Fetching health insights for user {user_ids}")
            
            # Fetch health insights from the database
            health_insights = await self.health_insights_repo.get_by_user_ids(user_ids)
            
            if health_insights:
                self.logger.info(f"Successfully fetched health insights for user {user_ids}")
                return health_insights
            else:
                self.logger.info(f"No health insights found for user {user_ids}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error fetching health insights for user {user_ids}: {str(e)}", exc_info=e)
            return None
    
    async def generate(self, job_id: str = None) -> Dict[str, Any]:
        """
        Generate health insights.
        
        Args:
            job_id (str, optional): The job ID to use. If not provided, a new one will be generated.
            
        Returns:
            Dict[str, Any]: Dictionary containing the generated insights
        """
        self.logger.info("Generating health insights...")
    
        # Use provided job_id or generate a new one
        if not job_id:
            job_id = JobExecutionLogger.generate_job_id(HEALTH_INSIGHT_JOB_ID)
            self.logger.info(f"Generated new job ID: {job_id}")
        else:
            self.logger.info(f"Using provided job ID: {job_id}")
    
        job_start_time = datetime.utcnow()
        self.logger.info(f"Job start time: {job_start_time}")
    
        try:
            # Start a new transaction
            async with self.session.begin():
                # Log job start
                self.logger.info("Logging job start...")
                last_job_exec_time = await self.job_logger.get_last_execution_time(schedule_name=HEALTH_INSIGHT_JOB_ID)
                await self.job_logger.log_execution(
                    job_id=job_id,
                    status='STARTED',
                    schedule_name=HEALTH_INSIGHT_JOB_ID
                )
    
                # Fetch patient visit summaries created after job start
                self.logger.info("Fetching patient visit summaries...")
                grouped_patient_summaries = await self._fetch_patient_visit_summaries(last_job_exec_time)
                ## Lets call LLM to generate the Health Insights by iterating the user id and summaries... 
                self.logger.info("Generating health insights...")
                health_insights = await self._generate_health_insights(grouped_patient_summaries)
    
                ## Lets save the health insights to the database... 
            self.logger.info("Saving health insights to the database...")
            await self._save_health_insights(health_insights)
    
            total_summaries = sum(len(group.summaries) for group in grouped_patient_summaries.values())
            self.logger.info(f"Retrieved {len(grouped_patient_summaries)} users with {total_summaries} total summaries")
    
            result = {
                "status": "success",
                "message": "Health insights generation started",
                "user_count": len(grouped_patient_summaries),
                "total_summaries": total_summaries,
                "job_start_time": job_start_time.isoformat(),
                "job_id": job_id
            }
    
            # Log job completion
            self.logger.info("Logging job completion...")
            await self.job_logger.log_execution(job_id, 'COMPLETED')
    
            self.logger.info(f"Job completed successfully. Result: {result}")
            return result
    
        except Exception as e:
            # Log job failure
            self.logger.error(f"Job failed with error: {str(e)}", exc_info=e)
            try:
                async with self.session.begin():
                    await self.job_logger.log_execution(job_id, 'FAILED')
            except Exception as log_error:
                self.logger.error(f"Failed to log job failure: {str(log_error)}", exc_info=log_error)
            raise e