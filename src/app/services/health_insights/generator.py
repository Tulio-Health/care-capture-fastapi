import logging
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...db.objects.repositories.conversation_summaries import ConversationSummariesRepository
from ...db.objects.entities.conversation_summaries import ConversationSummaries
from ...common.scheduler.job_execution_db_log import JobExecutionLogger
from ...models.conversation_summaries import ConversationSummary
from ...constants.scheduler import HEALTH_INSIGHT_JOB_ID
from datetime import datetime

logger = logging.getLogger(__name__)

class HealthInsightGenerator:
    """Class responsible for generating health insights for all the patients."""
    
    def __init__(self, session: AsyncSession):
        """Initialize the health insight generator."""
        self.logger = logger
        self.session = session
        self.conversation_repo = ConversationSummariesRepository(session)
        self.job_logger = JobExecutionLogger(session)
    
    async def _fetch_patient_visit_summaries(self, job_start_time: datetime) -> List[ConversationSummary]:
        """
        Fetch visit summaries for all patients from conversation_summaries table
        that were created after the job start time.
        
        Args:
            job_start_time (datetime): The timestamp when the job started
            
        Returns:
            List[ConversationSummary]: List of patient visit summaries as Pydantic models
        """
        try:
            self.logger.info(f"Starting to fetch patient visit summaries created after {job_start_time}...")
            
            # Fetch conversation summaries created after job start time
            # query = select(ConversationSummaries).where(
            #     ConversationSummaries.created_at >= job_start_time
            # ).order_by(ConversationSummaries.created_at.desc())
            
            query = select(ConversationSummaries).order_by(ConversationSummaries.created_at.desc())
            
            self.logger.debug(f"Executing query: {query}")
            result = await self.session.execute(query)
            summaries = result.scalars().all()
            
            self.logger.info(f"Found {len(summaries)} summaries in database")
            
            # Convert to Pydantic models
            summaries_list = []
            for summary in summaries:
                try:
                    summary_model = ConversationSummary.model_validate(summary)
                    summaries_list.append(summary_model)
                except Exception as e:
                    self.logger.error(f"Error converting summary {summary.id} to Pydantic model: {str(e)}")
                    continue
            
            self.logger.info(f"Successfully converted {len(summaries_list)} summaries to Pydantic models")
            return summaries_list
            
        except Exception as e:
            self.logger.error(f"Error fetching patient visit summaries: {str(e)}", exc_info=e)
            raise
    
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
                await self.job_logger.log_execution(
                    job_id=job_id,
                    status='STARTED',
                    schedule_name=HEALTH_INSIGHT_JOB_ID
                )
                
                # Fetch patient visit summaries created after job start
                self.logger.info("Fetching patient visit summaries...")
                patient_summaries = await self._fetch_patient_visit_summaries(job_start_time)
                self.logger.info(f"Retrieved {len(patient_summaries)} new patient visit summaries")
                
                result = {
                    "status": "success",
                    "message": "Health insights generation started",
                    "patient_count": len(patient_summaries),
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