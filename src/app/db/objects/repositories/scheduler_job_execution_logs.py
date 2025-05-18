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
        log_entry = SchedulerJobExecutionLogs(
            job_id=job_id,
            schedule_name=schedule_name,
            start_time=datetime.utcnow(),
            status='RUNNING'
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry
    
    async def update_job_end(self, job_id: str, status: str) -> None:
        """
        Update a job execution log entry with end time and status.
        
        Args:
            job_id (str): The job ID
            status (str): The final status of the job
        """
        query = select(SchedulerJobExecutionLogs).where(
            SchedulerJobExecutionLogs.job_id == job_id,
            SchedulerJobExecutionLogs.end_time.is_(None)
        )
        result = await self.session.execute(query)
        log_entry = result.scalar_one_or_none()
        
        if log_entry:
            log_entry.end_time = datetime.utcnow()
            log_entry.status = status
            await self.session.flush()

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