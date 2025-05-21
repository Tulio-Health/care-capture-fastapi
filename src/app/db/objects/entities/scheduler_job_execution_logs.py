from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class SchedulerJobExecutionLogs(Base):
    """Entity representing scheduler job execution logs."""
    __tablename__ = "scheduler_job_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    job_id = Column(String(255), nullable=False)
    schedule_name = Column(String(255), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<SchedulerJobExecutionLogs(id={self.id}, job_id={self.job_id}, status={self.status})>" 