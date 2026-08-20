from sqlite3 import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..entities.conversation_summaries import ConversationSummaries
from typing import Any, Optional, List
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
    
    # async def get_by_appointment_id_and_source(
    #     self, 
    #     appointment_id: UUID, 
    #     source: str
    # ) -> Optional[ConversationSummaries]:
    #     """
    #     Get conversation summary by appointment_id and metadata source.
        
    #     Args:
    #         appointment_id: UUID of the appointment
    #         source: Source of the summary (e.g., 'fhir_analysis', 'transcript')
            
    #     Returns:
    #         ConversationSummaries object or None if not found
    #     """
    #     try:
    #         from sqlalchemy import cast, String
            
    #         result = await self.session.execute(
    #             select(ConversationSummaries).where(
    #                 ConversationSummaries.appointment_id == appointment_id,
    #                 cast(ConversationSummaries.summary_metadata["source"], String) == source
    #             )
    #         )
    #         return result.scalar_one_or_none()
    #     except Exception as e:
    #         logger.error(
    #             f"Error fetching summary for appointment_id: {appointment_id}, source: {source}", 
    #             exc_info=e
    #         )
    #         raise e

    async def get_by_appointment_id_and_source(
    self,
    appointment_id: UUID,
    source: str,
) -> Optional[ConversationSummaries]:

        """
        Get latest conversation summary by appointment_id and metadata source.
        """

        try:
            stmt = (
                select(ConversationSummaries)
                .where(
                    ConversationSummaries.appointment_id == appointment_id,
                    ConversationSummaries.summary_metadata.op("->>")("source") == source,
                )
                .order_by(ConversationSummaries.created_at.desc())  # get latest
                .limit(1)
            )

            result = await self.session.execute(stmt)
            return result.scalars().first()

        except Exception as e:
            logger.error(
                f"Error fetching summary for appointment_id: {appointment_id}, source: {source}",
                exc_info=True,
            )
            raise


    
    async def get_all_by_appointment_id_and_source(
        self,
        appointment_id: UUID,
        source: str,
    ) -> List[ConversationSummaries]:
        """
        Get ALL conversation summary rows for appointment_id + metadata source (not just the
        latest one) - the one-row-per-procedure model can have N rows for a single
        appointment+source, unlike the single-row sources (transcript/fhir_analysis/
        attachment_summary) that `get_by_appointment_id_and_source` still serves.
        """
        try:
            stmt = (
                select(ConversationSummaries)
                .where(
                    ConversationSummaries.appointment_id == appointment_id,
                    ConversationSummaries.summary_metadata.op("->>")("source") == source,
                )
                .order_by(ConversationSummaries.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            logger.error(
                f"Error fetching summaries for appointment_id: {appointment_id}, source: {source}",
                exc_info=True,
            )
            raise

    @staticmethod
    def _document_ids_key(summary_metadata: Any) -> str:
        """Deterministic, order-independent identity for a (consolidated) procedure row: the
        sorted, comma-joined `source_document_ids` from its metadata. A merged row's identity
        is therefore stable across re-syncs regardless of which contributing document happens
        to be listed first. Rows without `source_document_ids` (e.g. legacy single-row-per-
        appointment rows predating this key) resolve to "" and are always treated as stale by
        `upsert_many_for_source`, since "" never matches a real row's key.
        """
        ids = (summary_metadata or {}).get("source_document_ids") or []
        return ",".join(sorted(ids))

    async def upsert_many_for_source(
        self,
        appointment_id: UUID,
        source: str,
        rows: List[dict],
    ) -> List[ConversationSummaries]:
        """
        Replace ALL conversation_summaries rows for (appointment_id, source) with `rows` -
        "upsert-then-prune": each row is matched against an existing row by
        `_document_ids_key` (derived from `summary_metadata.source_document_ids`); a match
        updates the existing row in place (keeping its id/created_at), a non-match creates a
        new row, and any existing row whose key isn't present in `rows` is DELETED. This covers
        both a document being reclassified/removed since the last sync, and two previously-
        separate rows just having been consolidated into one (the old second row is deleted).

        Passing an empty `rows` list deletes every existing row for (appointment_id, source) -
        the correct "no procedures found" signal for the one-row-per-procedure model (no
        placeholder row is created).

        Each dict in `rows` must be a full summary_data dict (see `upsert`'s docstring for
        shape), with `summary_metadata` containing `source` and `source_document_ids`.
        """
        try:
            existing_rows = await self.get_all_by_appointment_id_and_source(appointment_id, source)
            existing_by_key = {
                self._document_ids_key(row.summary_metadata): row for row in existing_rows
            }

            result: List[ConversationSummaries] = []
            used_keys = set()
            for row_data in rows:
                key = self._document_ids_key(row_data.get("summary_metadata"))
                used_keys.add(key)
                existing_row = existing_by_key.get(key)
                if existing_row is not None:
                    for field_name, value in row_data.items():
                        if hasattr(existing_row, field_name):
                            setattr(existing_row, field_name, value)
                    result.append(existing_row)
                else:
                    new_row = ConversationSummaries(appointment_id=appointment_id, **row_data)
                    self.session.add(new_row)
                    result.append(new_row)

            stale_rows = [
                row for key, row in existing_by_key.items() if key not in used_keys
            ]
            for row in stale_rows:
                await self.session.delete(row)

            if stale_rows:
                logger.info(
                    f"Pruned {len(stale_rows)} stale conversation_summaries row(s) for "
                    f"appointment_id: {appointment_id}, source: {source}"
                )

            await self.session.commit()
            for row in result:
                await self.session.refresh(row)

            return result
        except Exception:
            await self.session.rollback()
            logger.error(
                f"Error upserting summaries for appointment_id: {appointment_id}, source: {source}",
                exc_info=True,
            )
            raise

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