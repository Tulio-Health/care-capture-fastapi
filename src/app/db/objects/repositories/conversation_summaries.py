import asyncio
from sqlalchemy.exc import IntegrityError
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from ..entities.conversation_summaries import ConversationSummaries
from typing import Any, Optional, List
from ....common.logging import get_logger
from uuid import UUID

logger = get_logger(__name__)


def _retry_transaction(operation):
    """One fresh transaction only for database-confirmed aborts; never uncertain commits."""
    from functools import wraps
    @wraps(operation)
    async def wrapped(self, *args, **kwargs):
        for attempt in range(2):
            try:
                return await operation(self, *args, **kwargs)
            except Exception as exc:
                current, seen, aborted = exc, set(), False
                while current is not None and id(current) not in seen:
                    seen.add(id(current))
                    original = getattr(current, "orig", current)
                    if getattr(original, "sqlstate", getattr(original, "pgcode", None)) in {"40001", "40P01", "55P03"}:
                        aborted = True
                    current = current.__cause__ or current.__context__
                if attempt or not aborted:
                    raise
                await self.session.rollback()
    return wrapped


async def appointment_belongs_to(session, appointment_id, user_id) -> bool:
    """Shared appointment-ownership predicate: does `appointment_id` belong to `user_id`?
    Same cast-to-String comparison as `ConversationSummariesRepository._lock_scope` uses -
    `appointments.user_id` is a plain String column while callers pass a UUID user id, so the
    comparison must cast explicitly or it silently no-matches.
    """
    from src.app.db.models.appointments import Appointment
    from sqlalchemy import cast, String
    result = await session.execute(select(Appointment.id).where(
        Appointment.id == appointment_id, cast(Appointment.user_id, String) == str(user_id)))
    return result.scalar_one_or_none() is not None


def _attempt_at(value):
    """Parse an `attempt_started_at` ISO-8601 string into a comparable, timezone-aware
    datetime, so a 'Z'-suffixed and a '+00:00'-suffixed timestamp for the same instant
    compare equal instead of being compared as unequal raw strings. A naive (no offset)
    timestamp is treated as UTC. An empty/missing value normalizes to the minimum
    representable datetime so it always sorts older than any real timestamp.
    """
    from datetime import datetime, timezone
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class ConversationSummariesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _lock_scope(self, appointment_id, source, user_id=None):
        """Serialize publication using PostgreSQL transaction locks; no schema changes."""
        import hashlib
        if user_id is not None and not await appointment_belongs_to(self.session, appointment_id, user_id):
            raise ValueError("APPOINTMENT_SCOPE_MISMATCH")
        key = int.from_bytes(hashlib.sha256(f"{appointment_id}:{source}".encode()).digest()[:8], "big", signed=True)
        await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await self.session.execute(select(__import__("sqlalchemy").func.pg_advisory_xact_lock(key)))

    @staticmethod
    def _validate_payload(payload):
        from src.app.services.document_extraction import DocumentProcessingError
        for field in ("summary_metadata", "data", "key_points", "medications", "diagnoses", "instructions", "recommendations"):
            try:
                serialized = json.dumps(payload.get(field), ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise DocumentProcessingError("INVALID_PERSISTENCE_PAYLOAD") from exc
            if len(serialized.encode()) > 256 * 1024:
                raise DocumentProcessingError("PERSISTENCE_PAYLOAD_TOO_LARGE")

    async def _commit_validated(self, rows, *, deleted_ids=()):
        from src.app.models.conversation_summaries import ConversationSummary
        # Validate the final merged JSON, including preserved metadata, before writing.
        for row in rows:
            self._validate_payload({name: getattr(row, name) for name in ("summary_metadata", "data", "key_points", "medications", "diagnoses", "instructions", "recommendations")})
        # Resolve defaults and validate the public contract BEFORE committing.
        await self.session.flush()
        for row in rows:
            await self.session.refresh(row)
            ConversationSummary.model_validate(row)
        # A lost commit acknowledgement must not trigger a second clinical write.
        # Re-read the exact row identities and compare the complete intended payload.
        from copy import deepcopy
        fields = ("user_id", "summary_text", "summary_metadata", "data", "key_points",
                  "medications", "diagnoses", "instructions", "recommendations")
        expected = [(row.id, {name: deepcopy(getattr(row, name)) for name in fields}) for row in rows]
        commit_task = asyncio.create_task(self.session.commit())
        try:
            await asyncio.shield(commit_task)
        except asyncio.CancelledError:
            # Keep the session alive briefly to settle an in-flight commit. Never
            # publish a failure placeholder or retry a write on cancellation.
            try:
                await asyncio.wait_for(asyncio.shield(commit_task), timeout=5)
            except (Exception, asyncio.CancelledError):
                commit_task.cancel()
                await asyncio.gather(commit_task, return_exceptions=True)
            raise
        except Exception as exc:
            from src.app.services.document_extraction import DocumentProcessingError
            try:
                await self.session.rollback()
                reconciled = bool(expected or deleted_ids)
                for identity, values in expected:
                    stored = await self.get_by_id(identity)
                    reconciled = reconciled and stored is not None and all(getattr(stored, name) == value for name, value in values.items())
                for identity in deleted_ids:
                    reconciled = (await self.get_by_id(identity)) is None and reconciled
                if reconciled:
                    return
            except Exception:
                pass
            raise DocumentProcessingError("PERSISTENCE_FAILED") from exc

    @_retry_transaction
    async def record_processing_failure(self, appointment_id, source, user_id, errors):
        await self._lock_scope(appointment_id, source, user_id)
        rows = await self.get_all_by_appointment_id_and_source(appointment_id, source)
        from src.app.services.summary_outcomes import outcome_metadata
        failure_metadata = outcome_metadata("unavailable", errors)
        preserved = []
        for row in rows:
            metadata = row.summary_metadata or {}
            if str(row.user_id) != str(user_id) or metadata.get("validation_status") != "passed":
                continue
            previous_attempt = max(metadata.get("attempt_started_at", ""), (metadata.get("last_refresh_outcome") or {}).get("attempt_started_at", ""))
            if previous_attempt > failure_metadata["attempt_started_at"]:
                preserved.append(row)
                continue
            row.summary_metadata = {**metadata, "last_refresh_outcome": failure_metadata}
            notice = "We couldn’t update this summary. The previous summary is shown below.\n\n"
            if not row.summary_text.startswith(notice):
                row.summary_text = notice + row.summary_text
            preserved.append(row)
        await self._commit_validated(preserved)
        return preserved

    async def create(self, conversation_summary: dict) -> ConversationSummaries:
        try:
            db_summary = ConversationSummaries(**conversation_summary)
            self.session.add(db_summary)
            await self._commit_validated([db_summary])
            return db_summary

        except IntegrityError as e:
            await self.session.rollback()
            logger.error("Error creating conversation summary", exc_info=False)
            raise e
        except Exception as e:
            logger.error("Error creating conversation summary", exc_info=False)
            raise e

    async def get_by_id(self, summary_id: UUID) -> Optional[ConversationSummaries]:
        try:
            result = await self.session.execute(
                select(ConversationSummaries).where(ConversationSummaries.id == summary_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching summary with ID: {summary_id}", exc_info=False)
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
            logger.error(f"Error fetching summary for transcript ID: {appointment_id}", exc_info=False)
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
    #             exc_info=False
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
                exc_info=False,
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
                exc_info=False,
            )
            raise

    @staticmethod
    def _document_ids_key(summary_metadata: Any) -> str:
        """Deterministic, order-independent identity for a (consolidated) procedure row: the
        sorted, comma-joined `source_document_ids` from its metadata. A merged row's identity
        is therefore stable across re-syncs regardless of which contributing document happens
        to be listed first. Rows without `source_document_ids` (e.g. legacy single-row-per-
        appointment rows predating this key) resolve to "" - `upsert_many_for_source` never
        matches or prunes these keyless rows; it collects them into `keyless_rows`, logs a
        warning, and leaves them untouched (never silently deleted).
        """
        if not isinstance(summary_metadata, dict):
            return ""
        ids = summary_metadata.get("source_document_ids") or []
        if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
            return ""
        return json.dumps(sorted(set(ids)), ensure_ascii=False, separators=(",", ":")) if ids else ""

    @_retry_transaction
    async def upsert_many_for_source(
        self,
        appointment_id: UUID,
        source: str,
        rows: List[dict],
        allow_prune: bool = False,
        user_id=None,
        attempt_started_at=None,
    ) -> List[ConversationSummaries]:
        """
        Replace conversation_summaries rows for (appointment_id, source) with `rows` -
        "upsert-then-prune": each row is matched against an existing row by
        `_document_ids_key` (derived from `summary_metadata.source_document_ids`); a match
        updates the existing row in place (keeping its id/created_at), a non-match creates a
        new row. An existing row whose key isn't present in `rows` is DELETED only when
        `allow_prune=True` AND an owner is established (from `rows[0]["user_id"]`, or the
        explicit `user_id` kwarg when `rows` is empty) - with `allow_prune=False` (the
        default) unmatched rows are kept and flagged with a "partial" outcome notice instead
        of being deleted. Existing rows with no `_document_ids_key` (legacy keyless rows) are
        never matched or pruned regardless of `allow_prune`; they are collected into
        `keyless_rows`, logged, and left untouched - deleting them is never automatic.

        Passing an empty `rows` list only deletes anything when `allow_prune=True` and an
        owner is established via `user_id` - the correct "no procedures found" signal for
        the one-row-per-procedure model (no placeholder row is created). Without
        `allow_prune`, an empty `rows` list is a no-op: nothing is deleted.

        Each dict in `rows` must be a full summary_data dict (see `upsert`'s docstring for
        shape), with `summary_metadata` containing `source` and `source_document_ids`.

        Locking caveat: `_lock_scope`'s advisory lock only serializes writers that go through
        this fastapi repository method - it is fastapi-internal serialization, not a
        table-wide exclusive lock. nodeapi has at least one live write path that updates
        conversation_summaries rows directly via TypeORM (e.g. re-pointing `appointmentId`
        on appointment merges in `appointment.service.ts`, unfiltered by `source`) without
        acquiring this lock.
        """
        try:
            owner_id = rows[0]["user_id"] if rows else user_id
            if allow_prune and owner_id is None:
                raise ValueError("EMPTY_REPLACEMENT_REQUIRES_OWNER")
            if any(str(row_data.get("user_id")) != str(owner_id) for row_data in rows):
                raise ValueError("SUMMARY_SCOPE_MISMATCH")
            await self._lock_scope(appointment_id, source, owner_id)
            for row_data in rows:
                self._validate_payload(row_data)
            existing_rows = await self.get_all_by_appointment_id_and_source(appointment_id, source)
            if owner_id is not None and any(str(row.user_id) != str(owner_id) for row in existing_rows):
                raise ValueError("SUMMARY_SCOPE_MISMATCH")
            incoming_started = (rows[0].get("summary_metadata") or {}).get("attempt_started_at", "") if rows else attempt_started_at
            if incoming_started and any(_attempt_at((row.summary_metadata or {}).get("attempt_started_at", "")) > _attempt_at(incoming_started) for row in existing_rows):
                await self.session.rollback()
                return existing_rows
            existing_by_key = {}
            keyless_rows = []
            for row in existing_rows:
                key = self._document_ids_key(row.summary_metadata)
                if key:
                    existing_by_key.setdefault(key, row)
                else:
                    keyless_rows.append(row)
            if keyless_rows:
                logger.warning(
                    f"Retaining {len(keyless_rows)} keyless conversation_summaries row(s) "
                    f"(no source_document_ids) for appointment_id: {appointment_id}, "
                    f"source: {source} - never eligible for pruning"
                )

            result: List[ConversationSummaries] = []
            used_keys = set()
            for row_data in rows:
                key = self._document_ids_key(row_data.get("summary_metadata"))
                if not key or key in used_keys:
                    raise ValueError("DUPLICATE_OR_MISSING_SUMMARY_IDENTITY")
                used_keys.add(key)
                existing_row = existing_by_key.get(key)
                if existing_row is not None:
                    for field_name, value in row_data.items():
                        if field_name in {"id", "appointment_id", "created_by", "created_at"}:
                            continue
                        if field_name == "summary_metadata":
                            value = {**(existing_row.summary_metadata or {}), **value}
                            value.pop("last_refresh_outcome", None)
                        if hasattr(existing_row, field_name):
                            setattr(existing_row, field_name, value)
                    result.append(existing_row)
                else:
                    new_row = ConversationSummaries(appointment_id=appointment_id, **row_data)
                    self.session.add(new_row)
                    result.append(new_row)

            stale_rows = [row for row in existing_rows if allow_prune and row not in result and row not in keyless_rows]
            if not allow_prune:
                for row in existing_rows:
                    if row in result:
                        continue
                    metadata = row.summary_metadata or {}
                    if metadata.get("validation_status") != "passed":
                        continue
                    row.summary_metadata = {**metadata, "last_refresh_outcome": {"processing_outcome": "partial"}}
                    notice = "We couldn’t update this summary. The previous summary is shown below.\n\n"
                    if not row.summary_text.startswith(notice):
                        row.summary_text = notice + row.summary_text
                    result.append(row)
            for row in stale_rows:
                await self.session.delete(row)

            if stale_rows:
                logger.info(
                    f"Pruned {len(stale_rows)} stale conversation_summaries row(s) for "
                    f"appointment_id: {appointment_id}, source: {source}"
                )

            await self._commit_validated(result, deleted_ids=tuple(row.id for row in stale_rows))
            return result
        except Exception:
            await self.session.rollback()
            logger.error(
                f"Error upserting summaries for appointment_id: {appointment_id}, source: {source}",
                exc_info=False,
            )
            raise

    @_retry_transaction
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

            self._validate_payload(summary_data)
            await self._lock_scope(appointment_id, source, summary_data["user_id"])
            # Try to find existing summary with same appointment_id and source
            db_summary = await self.get_by_appointment_id_and_source(appointment_id, source)

            if db_summary and str(db_summary.user_id) != str(summary_data["user_id"]):
                raise ValueError("SUMMARY_SCOPE_MISMATCH")
            if db_summary:
                incoming = summary_data.get("summary_metadata") or {}
                previous = db_summary.summary_metadata or {}
                if incoming.get("attempt_started_at") and _attempt_at(previous.get("attempt_started_at", "")) > _attempt_at(incoming["attempt_started_at"]):
                    await self.session.rollback()
                    return db_summary
                if incoming.get("processing_outcome") in {"unavailable", "no_documents"} and previous.get("processing_outcome") in {"complete", "partial"} and previous.get("validation_status") == "passed":
                    # Whole-dict assignment is required for plain SQLAlchemy JSON columns.
                    db_summary.summary_metadata = {**previous, "last_refresh_outcome": incoming}
                    notice = "We couldn’t update this summary. The previous summary is shown below.\n\n"
                    if not db_summary.summary_text.startswith(notice):
                        db_summary.summary_text = notice + db_summary.summary_text
                    await self._commit_validated([db_summary])
                    return db_summary
                summary_data["summary_metadata"] = {**previous, **incoming}
                summary_data["summary_metadata"].pop("last_refresh_outcome", None)
                # Update existing summary
                logger.info(
                    f"Updating existing summary for appointment_id: {appointment_id}, "
                    f"source: {source}, summary_id: {db_summary.id}"
                )
                for key, value in summary_data.items():
                    if key in {"id", "appointment_id", "created_by", "created_at"}:
                        continue
                    if hasattr(db_summary, key):
                        setattr(db_summary, key, value)
            else:
                # Create new summary
                logger.info(
                    f"Creating new summary for appointment_id: {appointment_id}, source: {source}"
                )
                db_summary = ConversationSummaries(appointment_id=appointment_id, **summary_data)
                self.session.add(db_summary)

            await self._commit_validated([db_summary])
            return db_summary
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Error upserting summary for appointment_id: {appointment_id}, "
                f"source: {summary_data.get('summary_metadata', {}).get('source', 'unknown')}",
                exc_info=False
            )
            raise e
