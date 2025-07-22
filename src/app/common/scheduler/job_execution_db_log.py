"""
Job Execution Logger Module

This module provides a common interface for logging job execution status across different schedulers.
It handles the creation and updating of job execution logs in the database, ensuring consistent
tracking of job lifecycle events.

Example:
    ```python
    from app.common.job_execution_logger import JobExecutionLogger
    from app.db.config.database import get_db

    async def some_scheduled_job():
        async for session in get_db():
            logger = JobExecutionLogger(session)
            job_id = f'job-name-{datetime.now().strftime("%m-%d-%Y:%H:%M:%S")}'
            
            try:
                await logger.log_execution(job_id, 'STARTED')
                # Do some work
                await logger.log_execution(job_id, 'COMPLETED')
            except Exception as e:
                await logger.log_execution(job_id, 'FAILED')
                raise e
    ```
"""

import logging
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from ...db.objects.repositories.scheduler_job_execution_logs import SchedulerJobExecutionLogsRepository
from ...db.objects.entities.scheduler_job_execution_logs import SchedulerJobExecutionLogs

logger = logging.getLogger(__name__)

class JobExecutionLogger:
    """
    A class to handle job execution logging across different schedulers.
    
    This class provides methods to log the start, completion, and failure of scheduled jobs.
    It ensures consistent logging of job execution status and maintains a record of job
    lifecycle events in the database.
    
    Attributes:
        session (AsyncSession): The database session for executing queries
        logs_repo (SchedulerJobExecutionLogsRepository): Repository for job execution logs
    """
    
    @staticmethod
    def generate_job_id(prefix: str) -> str:
        """
        Generate a unique job ID.
        
        Args:
            prefix (str): The prefix for the job ID
            
        Returns:
            str: The generated job ID
        """
        timestamp = datetime.utcnow().strftime("%m-%d-%Y:%H:%M:%S")
        return f"{prefix}-{timestamp}"
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the JobExecutionLogger.
        
        Args:
            session (AsyncSession): The database session to use for logging
        """
        self.session = session
        self.logs_repo = SchedulerJobExecutionLogsRepository(session)
    
    async def log_execution(self, job_id: str, status: str, schedule_name: Optional[str] = None) -> None:
        """
        Log a job execution.
        
        Args:
            job_id (str): The job ID
            status (str): The status of the job execution
            schedule_name (str, optional): The name of the schedule
        """
        try:
            if status == 'STARTED':
                await self.logs_repo.create_job_start(job_id, schedule_name)
            elif status in ['COMPLETED', 'FAILED']:
                await self.logs_repo.update_job_end(job_id, status)
            else:
                logger.warning(f"Unknown status: {status}")
        except Exception as e:
            logger.error(f"Error logging job execution: {str(e)}", exc_info=e)
            raise 
        
    async def get_last_execution_time(self , schedule_name: str) -> Optional[datetime]:
        """Get the last execution time for a job."""
        try:
            return await self.logs_repo.get_last_execution_time(schedule_name=schedule_name)
        except Exception as e:
            logger.error(f"Error fetching last execution time: {str(e)}", exc_info=e)
            raise