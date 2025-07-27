from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from ..services.health_insights.health_insight_generator import HealthInsightGenerator
from ..db.config.database import get_db
from ..common.scheduler.job_execution_db_log import JobExecutionLogger
from ..constants.scheduler import HEALTH_INSIGHT_JOB_ID, HEALTH_INSIGHT_SCHEDULE_SECONDS
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

async def generate_health_insight():
    """Function to generate health insights periodically."""
    try:
        # Get database session
        async for session in get_db():
            try:
                # Generate job ID with timestamp
                job_id = JobExecutionLogger.generate_job_id(HEALTH_INSIGHT_JOB_ID)
                
                # Generate insights
                generator = HealthInsightGenerator(session)
                result = await generator.generate(job_id=job_id)
                logger.info(f"Health insight generation result: {result}")
                
                break
            except Exception as e:
                logger.error(f"Error in database operations: {str(e)}", exc_info=e)
                raise e
    except Exception as e:
        logger.error(f"Error in health insight generation: {str(e)}", exc_info=e)
        raise e

def init_scheduler():
    """Initialize and start the scheduler."""
    scheduler = AsyncIOScheduler()
    
    # Add the health insight generation job
    scheduler.add_job(
        func=generate_health_insight,
        trigger=IntervalTrigger(seconds=HEALTH_INSIGHT_SCHEDULE_SECONDS),
        id='generate_health_insight',
        name='Generate health insights every ' + str(HEALTH_INSIGHT_SCHEDULE_SECONDS) + ' seconds',
        replace_existing=True
    )
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started successfully")
    
    return scheduler 