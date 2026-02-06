from sqlite3 import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..entities.conversation_summaries import ConversationSummaries
from typing import Optional, List
from ....common.logging import get_logger
from uuid import UUID

logger = get_logger(__name__)

class ConversationSummariesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, conversation_summary: dict) -> ConversationSummaries:
        try:
            print(conversation_summary)
            db_summary = ConversationSummaries(**conversation_summary)
            self.session.add(db_summary)
            await self.session.commit()
            await self.session.refresh(db_summary)
            return db_summary
        
        except IntegrityError as e:
            await self.session.rollback()
            logger.error("Error creating conversation summary", exc_info=e)
            raise e
        except Exception as e:
            logger.error("Error creating conversation summary", exc_info=e)
            raise e

    async def get_by_id(self, summary_id: UUID) -> Optional[ConversationSummaries]:
        try:
            result = await self.session.execute(
                select(ConversationSummaries).where(ConversationSummaries.id == summary_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching summary with ID: {summary_id}", exc_info=e)
            raise e

    async def get_by_appointment_id(self, appointment_id: UUID) -> Optional[ConversationSummaries]:
        try:
            result = await self.session.execute(
                select(ConversationSummaries).where(
                    ConversationSummaries.appointment_id == appointment_id
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching summary for transcript ID: {appointment_id}", exc_info=e)
            raise e
    
    async def get_by_appointment_id_and_source(
        self, 
        appointment_id: UUID, 
        source: str
    ) -> Optional[ConversationSummaries]:
        """
        Get conversation summary by appointment_id and metadata source.
        
        Args:
            appointment_id: UUID of the appointment
            source: Source of the summary (e.g., 'fhir_analysis', 'transcript')
            
        Returns:
            ConversationSummaries object or None if not found
        """
        try:
            from sqlalchemy import cast, String
            
            result = await self.session.execute(
                select(ConversationSummaries).where(
                    ConversationSummaries.appointment_id == appointment_id,
                    cast(ConversationSummaries.summary_metadata["source"], String) == source
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Error fetching summary for appointment_id: {appointment_id}, source: {source}", 
                exc_info=e
            )
            raise e
    
    async def get_by_user_id(self, user_id: UUID) -> Optional[ConversationSummaries]:
        try:
            result = await self.session.execute(
                select(ConversationSummaries).where(
                    ConversationSummaries.user_id == user_id
                )
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching summary for user ID: {user_id}", exc_info=e)
            raise e

    async def update(self, summary_id: UUID, summary_data: dict) -> Optional[ConversationSummaries]:
        try:
            db_summary = await self.get_by_id(summary_id)
            if db_summary:
                for key, value in summary_data.items():
                    if hasattr(db_summary, key):
                        setattr(db_summary, key, value)
                await self.session.commit()
                await self.session.refresh(db_summary)
            return db_summary
        except Exception as e:
            logger.error(f"Error updating summary with ID: {summary_id}", exc_info=e)
            raise e

    async def delete(self, summary_id: UUID) -> bool:
        try:
            db_summary = await self.get_by_id(summary_id)
            if db_summary:
                await self.session.delete(db_summary)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting summary with ID: {summary_id}", exc_info=e)
            raise e
        
    async def upsert(self, appointment_id: UUID, summary_data: dict) -> Optional[ConversationSummaries]:
        """
        Upsert a conversation summary based on appointment_id and metadata source.
        If a summary with the same appointment_id and source exists, update it.
        Otherwise, create a new summary.
        
        Args:
            appointment_id: UUID of the appointment
            summary_data: Dictionary containing summary fields (must include summary_metadata with source)
            
        Returns:
            ConversationSummaries object (created or updated)
        """
        try:
            # Extract source from metadata
            source = summary_data.get("summary_metadata", {}).get("source", "unknown")
            
            # Try to find existing summary with same appointment_id and source
            db_summary = await self.get_by_appointment_id_and_source(appointment_id, source)
            
            if db_summary:
                # Update existing summary
                logger.info(
                    f"Updating existing summary for appointment_id: {appointment_id}, "
                    f"source: {source}, summary_id: {db_summary.id}"
                )
                for key, value in summary_data.items():
                    if hasattr(db_summary, key):
                        setattr(db_summary, key, value)
            else:
                # Create new summary
                logger.info(
                    f"Creating new summary for appointment_id: {appointment_id}, source: {source}"
                )
                db_summary = ConversationSummaries(appointment_id=appointment_id, **summary_data)
                self.session.add(db_summary)
            
            await self.session.commit()
            await self.session.refresh(db_summary)
            return db_summary
        except Exception as e:
            logger.error(
                f"Error upserting summary for appointment_id: {appointment_id}, "
                f"source: {summary_data.get('summary_metadata', {}).get('source', 'unknown')}", 
                exc_info=e
            )
            raise e
    
    async def create_with_metadata(
        self, 
        summary_data: dict, 
        source: str = "fhir_analysis"
    ) -> ConversationSummaries:
        """
        Create a conversation summary with metadata indicating the source
        
        Args:
            summary_data: Dictionary containing summary fields
            source: Source of the summary (e.g., 'fhir_analysis', 'transcript_summarization')
            
        Returns:
            Created ConversationSummaries object
        """
        try:
            from datetime import datetime
            
            # Add metadata to the summary data
            if "metadata" not in summary_data:
                summary_data["metadata"] = {}
            
            summary_data["metadata"]["source"] = source
            summary_data["metadata"]["created_at"] = datetime.utcnow().isoformat()
            summary_data["metadata"]["analysis_version"] = "1.0"
            
            return await self.create(summary_data)
        except Exception as e:
            logger.error(f"Error creating summary with metadata: {e}", exc_info=e)
            raise e