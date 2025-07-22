from operator import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
from ..entities.scheduler_job_execution_logs import SchedulerJobExecutionLogs
from ....common.logging import get_logger

logger = get_logger(__name__)

class SchedulerJobExecutionLogsRepository:
    """Repository for scheduler job execution logs."""
    
    def __init__(self, session: AsyncSession):
        """Initialize the repository."""
        self.session = session
    
    async def create_job_start(self, job_id: str, schedule_name: str) -> SchedulerJobExecutionLogs:
        """
        Create a new job execution log entry.
        
        Args:
            job_id (str): The job ID
            schedule_name (str): The name of the schedule
            
        Returns:
            SchedulerJobExecutionLogs: The created log entry
        """
        try:
            log_entry = SchedulerJobExecutionLogs(
                job_id=job_id,
                schedule_name=schedule_name,
                start_time=datetime.now(),
                status='RUNNING'
            )
            self.session.add(log_entry)
            await self.session.flush()
            return log_entry
        except Exception as e:
            logger.error(f"Error creating job execution log: {str(e)}", exc_info=e)
            raise
    
    async def update_job_end(self, job_id: str, status: str) -> None:
        """
        Update a job execution log entry with end time and status.
        
        Args:
            job_id (str): The job ID
            status (str): The final status of the job
        """
        try:
            query = select(SchedulerJobExecutionLogs).where(
            SchedulerJobExecutionLogs.job_id == job_id,
            SchedulerJobExecutionLogs.end_time.is_(None)
            )
            result = await self.session.execute(query)
            log_entry = result.scalar_one_or_none()
            
            if log_entry:
                log_entry.end_time = datetime.now()  # using now() instead of utcnow()
                log_entry.status = status
                await self.session.commit()  # using commit() instead of flush()
        except Exception as e:
            logger.error(f"Error updating job execution log: {str(e)}", exc_info=e)
            raise

    async def get_job_log(self, job_id: str) -> Optional[SchedulerJobExecutionLogs]:
        """Get the latest log entry for a job."""
        try:
            result = await self.session.execute(
                select(SchedulerJobExecutionLogs)
                .where(SchedulerJobExecutionLogs.job_id == job_id)
                .order_by(SchedulerJobExecutionLogs.start_time.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching job log: {str(e)}", exc_info=e)
            raise
        
    async def get_last_execution_time(self, schedule_name: str) -> Optional[datetime]:
        """Get the last execution time for a job."""
        try:
            result = await self.session.execute(
                select(SchedulerJobExecutionLogs)
                .where(
                    and_(
                        SchedulerJobExecutionLogs.schedule_name == schedule_name,
                        SchedulerJobExecutionLogs.status == 'COMPLETED'
                    )
                )
                .order_by(SchedulerJobExecutionLogs.start_time.desc())
                .limit(1)
            )
            log_entry = result.scalar_one_or_none()
            if log_entry:
                return log_entry.start_time
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching last execution time: {str(e)}", exc_info=e)
            raise