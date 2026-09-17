"""Procedure Summarization Service - Handles procedure document extraction and
patient-facing summarization.

Mirrors `AttachmentSummarizationService`'s fetch/download/extract pattern, but filters
DocumentReferences down to only those flagged `isProcedureDocument` (set by
care-capture-emr-connector from care-capture-fastapi's document-type-inference response)
and runs the batch-shaped `ProcedureExtractionChain` instead of the map-reduce
attachment_summarization chain. Produces one ProcedureSummary per procedure document, then
runs `ProcedureConsolidator` (see `chains/procedure_extraction/consolidation.py`) to collapse
extractions that describe the SAME real-world procedure event across multiple source
documents before persisting one `conversation_summaries` row per CONSOLIDATED procedure.
"""

from datetime import datetime
from typing import Any, List

from sqlalchemy import select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.procedure_extraction.chain import ProcedureExtractionChain
from src.app.chains.procedure_extraction.consolidation import (
    ConsolidatedProcedure,
    ProcedureConsolidator,
)
from src.app.common.logging import get_logger
from src.app.db.models.appointments import Appointment
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.conversation_summaries import ConversationSummary
from src.app.models.procedure_summarization import (
    ProcedureSummarizationRequest,
    ProcedureSummary,
)
from src.app.services.document_extraction import DocumentTextExtractor
from src.app.services.summary_outcomes import outcome_metadata, MESSAGES
from src.app.utils.s3_client import S3DocumentClient

from src.app.services.summary_runtime import bounded_summary

logger = get_logger(__name__)

_SOURCE = "procedure_summary"


def _build_summary_text(p: ProcedureSummary) -> str:
    """The patient-facing narrative for a procedure row's `summary_text` is exactly
    `procedure_details` - it's already real second-person narrative prose on its own,
    matching the single-paragraph prose convention every other `conversation_summaries`
    row uses (never a bare title). `procedure_type` and `procedure_date` are deliberately
    left out - they're available separately as `data.procedure_type`/`summary_metadata.
    procedure_date` for callers to compose their own header. `outcome` stays excluded too -
    it's already exposed separately as `data.outcome`.
    """
    return p.procedure_details


class ProcedureSummarizationService:
    """
    Service for extracting structured, patient-facing procedure summaries.

    This service handles:
    - Fetching DocumentReference resources with attachments for an encounter
    - Filtering to only documents flagged as procedure documents (isProcedureDocument=True)
    - Downloading documents from S3 and extracting text
    - Running the procedure-extraction chain
    - Consolidating extractions that describe the same real-world procedure event
    - Persisting one conversation_summaries row per consolidated procedure (see `_persist`)

    Follows the same fetch/download/extract architectural pattern as
    AttachmentSummarizationService, including owning its own persistence via
    ConversationSummariesRepository.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.fhir_repo = FhirResourcesRepository(db)
        self.summaries_repo = ConversationSummariesRepository(db)
        self.s3_client = S3DocumentClient()
        from src.app.core.settings import get_settings
        settings = get_settings()
        self.text_extractor = DocumentTextExtractor()
        self.logger = logger

    @bounded_summary
    async def analyze_procedures(
        self, request: ProcedureSummarizationRequest
    ) -> List[ConversationSummary]:
        """
        Extract structured procedure summaries for a patient appointment, consolidate
        extractions that describe the same real-world procedure event across multiple source
        documents, and persist one `conversation_summaries` row per CONSOLIDATED procedure via
        `ConversationSummariesRepository.upsert_many_for_source` - keyed on
        `summary_metadata.source = 'procedure_summary'` so these rows coexist with the
        transcript and fhir_analysis/attachment_summary rows for the same appointment.

        Returns an empty list (NOT an error, and NOT a placeholder row) when the appointment
        has no procedure documents, or all documents failed extraction, or every extracted
        procedure got consolidated away as a duplicate of another - an empty list is itself the
        correct "no procedures" signal for callers (nodeapi's procedure count check, mobile's
        "don't show the tab" behavior), and this endpoint degrades gracefully so callers that
        already gate on "does this appointment have a procedure doc" never see a hard failure
        just because that gate raced or a document was reclassified between calls.
        """
        self.logger.info(
            f"Starting procedure summarization - appointment_id: {request.appointment_id}, "
            f"user_id: {request.user_id}"
        )

        appointment = await self._fetch_appointment(request)

        doc_references = await self._fetch_procedure_document_references(request, appointment)

        if not doc_references:
            self.logger.info(
                f"No procedure documents found for appointment {request.appointment_id} - "
                "pruning any previously-persisted procedure_summary rows"
            )
            return await self._persist(request, consolidated=[], documents_analyzed=0, extraction_errors=[])

        from src.app.services.summary_outcomes import source_manifest
        initial_manifest = source_manifest(doc_references)
        extracted_documents = await self._process_attachments(doc_references)

        valid_documents = [doc for doc in extracted_documents if not doc.extraction_error]
        extraction_errors = [
            {"source_id": doc.resource_id or "unknown", "error": doc.extraction_error}
            for doc in extracted_documents
            if doc.extraction_error
        ]

        if not valid_documents:
            self.logger.warning(
                f"All procedure document extractions failed for appointment {request.appointment_id}"
            )
            return await self._persist(
                request, consolidated=[], documents_analyzed=0, extraction_errors=extraction_errors
            )

        chain = ProcedureExtractionChain()
        extracted, chain_failures = await chain.extract(valid_documents)
        # Merge chain-level LLM validation failures into the SAME extraction_errors list as
        # the S3/text-extraction failures above, so a document that downloaded fine but failed
        # LLM validation is no longer silently missing from both `extracted` and this list.
        extraction_errors.extend(chain_failures)

        consolidator = ProcedureConsolidator()
        consolidated = await consolidator.consolidate(extracted)
        current = await self._fetch_procedure_document_references(request, appointment)
        try:
            if source_manifest(current) != initial_manifest:
                raise ValueError("SOURCE_MANIFEST_CHANGED")
            await self.s3_client.validate_download_versions()
        except Exception:
            return await self._persist(request, [], 0, [{"error": "SOURCE_CHANGED"}])

        self.logger.info(
            f"Procedure summarization completed - appointment_id: {request.appointment_id}, "
            f"documents_extracted: {len(extracted)}, consolidated_procedures: {len(consolidated)}"
        )

        return await self._persist(
            request,
            consolidated=consolidated,
            documents_analyzed=len(valid_documents),
            extraction_errors=extraction_errors,
        )

    async def _persist(
        self,
        request: ProcedureSummarizationRequest,
        consolidated: List[ConsolidatedProcedure],
        documents_analyzed: int,
        extraction_errors: list,
    ) -> List[ConversationSummary]:
        """Upsert one conversation_summaries row per consolidated procedure (upsert-then-prune
        via `ConversationSummariesRepository.upsert_many_for_source` - see its docstring),
        replacing the old single-row-per-appointment model. `documents_analyzed` and
        `extraction_errors` are appointment/batch-level facts (not facts about any individual
        procedure), so they are logged here rather than written into any per-procedure row.
        This drops them from the HTTP response entirely (the old single-row shape returned them
        in `metadata.documents_analyzed`/`metadata.extraction_errors`) - confirmed safe for
        today's only caller, nodeapi's `createProcedureSummaryForAppointment`, which only reads
        the response's length/count and does not read either field today.
        """
        if documents_analyzed or extraction_errors:
            self.logger.info(
                f"Procedure summarization batch stats - appointment_id: {request.appointment_id}, "
                f"documents_analyzed: {documents_analyzed}, extraction_errors: {len(extraction_errors)}"
            )
        if extraction_errors:
            self.logger.warning(
                f"Procedure extraction errors for appointment {request.appointment_id}: {extraction_errors}"
            )

        if not consolidated and documents_analyzed and not extraction_errors:
            # Authoritative, fully successful extraction found no performed events.
            preserved = await self.summaries_repo.upsert_many_for_source(request.appointment_id, _SOURCE, [], allow_prune=True,
                user_id=request.user_id, attempt_started_at=outcome_metadata("complete")["attempt_started_at"])
            return [ConversationSummary.model_validate(row) for row in preserved]
        if not consolidated:
            # Empty or unsuccessful inventory is not proof of deletion. Retain last good rows.
            if extraction_errors:
                existing = await self.summaries_repo.record_processing_failure(request.appointment_id, _SOURCE, request.user_id, extraction_errors)
                if not existing:
                    from src.app.services.document_extraction import DocumentProcessingError
                    raise DocumentProcessingError("PROCEDURE_SUMMARY_UNAVAILABLE")
            else:
                existing = await self.summaries_repo.record_processing_failure(request.appointment_id, _SOURCE, request.user_id, [{"error": "NO_CURRENT_PROCEDURE_DOCUMENTS"}])
            return [ConversationSummary.model_validate(row) for row in existing if str(row.user_id) == str(request.user_id)]
        rows = []
        for item in consolidated:
            p = item.summary
            summary_metadata: dict = {
                "source": _SOURCE,
                **outcome_metadata("partial" if extraction_errors else "complete", extraction_errors),
                "processing_errors": extraction_errors,
                "pipeline_version": "document-safety-1",
                "is_clinical_summary": True,
                "validation_status": "passed",
                "summaryType": "procedure",
                "source_document_title": p.source_document_title,
                "source_document_ids": sorted(item.document_ids),
                "procedure_date": p.procedure_date,
                "performed_by": p.performed_by,
                "follow_up_source_quote": p.follow_up_source_quote,
            }
            if item.source_count > 1:
                summary_metadata["consolidated_from_document_count"] = item.source_count

            rows.append(
                {
                    "user_id": request.user_id,
                    "created_by": request.user_id,
                    "updated_by": request.user_id,
                    "summary_text": (MESSAGES["partial"] + "\n\n" if extraction_errors else "") + _build_summary_text(p),
                    "data": {
                        "procedure_type": p.procedure_type,
                        "reason": p.reason,
                        "procedure_details": p.procedure_details,
                        "outcome": p.outcome,
                        "follow_up": p.follow_up,
                    },
                    "key_points": None,
                    "medications": None,
                    "diagnoses": None,
                    "instructions": None,
                    "recommendations": None,
                    "summary_metadata": summary_metadata,
                }
            )

        db_summaries = await self.summaries_repo.upsert_many_for_source(
            appointment_id=request.appointment_id,
            source=_SOURCE,
            rows=rows,
            allow_prune=not extraction_errors,
        )
        return [ConversationSummary.model_validate(s) for s in db_summaries]

    async def _fetch_appointment(self, request: ProcedureSummarizationRequest) -> Appointment:
        appointment_stmt = select(Appointment).where(Appointment.id == request.appointment_id, cast(Appointment.user_id, String) == str(request.user_id))
        appointment_result = await self.db.execute(appointment_stmt)
        appointment = appointment_result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {request.appointment_id} not found")

        return appointment

    async def _fetch_procedure_document_references(
        self, request: ProcedureSummarizationRequest, appointment: Appointment
    ) -> List[Any]:
        if not appointment.ehr_entity_id:
            raise ValueError(
                f"Appointment {request.appointment_id} has no EHR entity ID - cannot fetch document attachments"
            )

        doc_references = await self.fhir_repo.get_document_references_with_attachments(
            user_id=str(request.user_id),
            encounter_id=appointment.ehr_entity_id,
        )

        procedure_doc_references = [
            doc_ref for doc_ref in doc_references if isinstance(doc_ref.data, dict) and doc_ref.data.get("isProcedureDocument") is True
        ]

        self.logger.debug(
            f"Fetched {len(doc_references)} DocumentReference(s), "
            f"{len(procedure_doc_references)} flagged as procedure documents - "
            f"appointment_id: {request.appointment_id}"
        )

        return procedure_doc_references

    async def _process_attachments(self, doc_references: List[Any]) -> List[DocumentAttachment]:
        from src.app.services.document_ingestion import process_attachments
        return await process_attachments(doc_references, self.s3_client, self.text_extractor)
