from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from ..services.health_insights.health_insight_generator import HealthInsightGenerator
from ..db.config.database import get_db, get_engine
from sqlalchemy import text
from ..common.scheduler.job_execution_db_log import JobExecutionLogger
from ..constants.scheduler import HEALTH_INSIGHT_JOB_ID, HEALTH_INSIGHT_SCHEDULE_SECONDS
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

async def generate_health_insight():
    """Single publisher across workers, using an existing PostgreSQL advisory lock."""
    async with asyncio.timeout(300):
        async with get_engine().begin() as coordination:
            acquired = await coordination.scalar(text("SELECT pg_try_advisory_xact_lock(6847239102)"))
            if not acquired:
                return
            async for session in get_db():
                job_id = JobExecutionLogger.generate_job_id(HEALTH_INSIGHT_JOB_ID)
                generator = HealthInsightGenerator(session)
                await generator.generate(job_id=job_id)
                break


def init_scheduler():
    """Initialize and start the scheduler."""
    scheduler = AsyncIOScheduler()

    # Add the health insight generation job
    scheduler.add_job(
        func=generate_health_insight,
        trigger=IntervalTrigger(seconds=HEALTH_INSIGHT_SCHEDULE_SECONDS),
        id='generate_health_insight',
        name='Generate health insights every ' + str(HEALTH_INSIGHT_SCHEDULE_SECONDS) + ' seconds',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started successfully")

    return scheduler
