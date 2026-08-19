"""Procedure Summarization Service - Handles procedure document extraction and
patient-facing summarization.

Mirrors `AttachmentSummarizationService`'s fetch/download/extract pattern, but filters
DocumentReferences down to only those flagged `isProcedureDocument` (set by
care-capture-emr-connector from care-capture-fastapi's document-type-inference response)
and runs the batch-shaped `ProcedureExtractionChain` instead of the map-reduce
attachment_summarization chain. Produces ONE ProcedureSummary per procedure document —
no cross-document synthesis/deduplication, since each procedure is its own distinct event.
"""

from datetime import datetime
from typing import Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.procedure_extraction.chain import ProcedureExtractionChain
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
)
from src.app.services.document_extraction import DocumentTextExtractor
from src.app.utils.s3_client import S3DocumentClient

logger = get_logger(__name__)


class ProcedureSummarizationService:
    """
    Service for extracting structured, patient-facing procedure summaries.

    This service handles:
    - Fetching DocumentReference resources with attachments for an encounter
    - Filtering to only documents flagged as procedure documents (isProcedureDocument=True)
    - Downloading documents from S3 and extracting text
    - Running the procedure-extraction chain
    - Returning one ProcedureSummary per procedure document

    Follows the same architectural pattern as AttachmentSummarizationService, minus
    database persistence (the caller — care-capture-nodeapi — owns persistence via
    ConversationSummaryEntity).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.fhir_repo = FhirResourcesRepository(db)
        self.summaries_repo = ConversationSummariesRepository(db)
        self.s3_client = S3DocumentClient()
        self.text_extractor = DocumentTextExtractor()
        self.logger = logger

    async def analyze_procedures(
        self, request: ProcedureSummarizationRequest
    ) -> ConversationSummary:
        """
        Extract structured procedure summaries for a patient appointment and persist them via
        `ConversationSummariesRepository.upsert` (same shared `conversation_summaries` table
        and appointment_id+source upsert key as `AttachmentSummarizationService`), keyed on
        `summary_metadata.source = 'procedure_summary'` so it coexists with the transcript and
        fhir_analysis/attachment_summary rows for the same appointment.

        Returns a ConversationSummary with an empty procedures list in metadata (not an error)
        when the appointment has no procedure documents - this endpoint degrades gracefully so
        callers that already gate on "does this appointment have a procedure doc" never see a
        hard failure just because that gate raced or a document was reclassified between calls.
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
                "persisting empty procedure summary"
            )
            return await self._persist(request, procedures=[], documents_analyzed=0, extraction_errors=[])

        extracted_documents = await self._process_attachments(doc_references)

        valid_documents = [doc for doc in extracted_documents if not doc.extraction_error]
        extraction_errors = [
            {"file_path": doc.file_path, "error": doc.extraction_error}
            for doc in extracted_documents
            if doc.extraction_error
        ]

        if not valid_documents:
            self.logger.warning(
                f"All procedure document extractions failed for appointment {request.appointment_id}"
            )
            return await self._persist(
                request, procedures=[], documents_analyzed=0, extraction_errors=extraction_errors
            )

        chain = ProcedureExtractionChain()
        procedures, chain_failures = await chain.extract(valid_documents)
        # Merge chain-level LLM validation failures into the SAME extraction_errors list as
        # the S3/text-extraction failures above, so a document that downloaded fine but failed
        # LLM validation is no longer silently missing from both `procedures` and this list.
        extraction_errors.extend(chain_failures)

        self.logger.info(
            f"Procedure summarization completed - appointment_id: {request.appointment_id}, "
            f"procedures_extracted: {len(procedures)}"
        )

        return await self._persist(
            request,
            procedures=procedures,
            documents_analyzed=len(valid_documents),
            extraction_errors=extraction_errors,
        )

    async def _persist(
        self,
        request: ProcedureSummarizationRequest,
        procedures: list,
        documents_analyzed: int,
        extraction_errors: list,
    ) -> ConversationSummary:
        """Build the patient-facing summary_text/key_points/instructions from the extracted
        procedures and upsert into conversation_summaries, mirroring
        AttachmentSummarizationService._prepare_summary_data's shape."""
        procedure_dicts = [p.model_dump() for p in procedures]

        if procedures:
            summary_text = "\n\n".join(
                f"{p.procedure_type}"
                + (f" ({p.procedure_date})" if p.procedure_date else "")
                + f": {p.procedure_details} {p.outcome}"
                for p in procedures
            )
            key_points = [f"{p.procedure_type}: {p.outcome}" for p in procedures]
            instructions = [p.follow_up for p in procedures]
        else:
            summary_text = "No procedure documents were found for this appointment."
            key_points = []
            instructions = []

        summary_data = {
            "summary_text": summary_text,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": key_points,
            "medications": [],
            "diagnoses": [],
            "instructions": instructions,
            "recommendations": [],
            "summary_metadata": {
                "source": "procedure_summary",
                "summaryType": "procedure",
                "procedures": procedure_dicts,
                "documents_analyzed": documents_analyzed,
                "extraction_errors": extraction_errors,
            },
        }

        db_summary = await self.summaries_repo.upsert(
            appointment_id=request.appointment_id, summary_data=summary_data
        )
        return ConversationSummary.model_validate(db_summary)

    async def _fetch_appointment(self, request: ProcedureSummarizationRequest) -> Appointment:
        appointment_stmt = select(Appointment).where(Appointment.id == request.appointment_id)
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
            doc_ref for doc_ref in doc_references if doc_ref.data.get("isProcedureDocument") is True
        ]

        self.logger.debug(
            f"Fetched {len(doc_references)} DocumentReference(s), "
            f"{len(procedure_doc_references)} flagged as procedure documents - "
            f"appointment_id: {request.appointment_id}"
        )

        return procedure_doc_references

    async def _process_attachments(self, doc_references: List[Any]) -> List[DocumentAttachment]:
        """Download and extract text from all procedure-document attachments. Mirrors
        AttachmentSummarizationService._process_attachments exactly (same S3/extraction
        pattern), scoped to the already-filtered procedure doc_references."""
        extracted_documents: List[DocumentAttachment] = []

        for doc_ref in doc_references:
            attachments_data = doc_ref.data.get("attachments")
            if not attachments_data:
                continue

            attachments = attachments_data if isinstance(attachments_data, list) else [attachments_data]

            for attachment in attachments:
                file_path = attachment.get("filePath")
                try:
                    if attachment.get("downloadStatus") != "success":
                        self.logger.debug(
                            f"Skipping attachment with status '{attachment.get('downloadStatus')}' "
                            f"for document {doc_ref.ehr_resource_id}"
                        )
                        continue

                    if not file_path:
                        self.logger.warning(f"Attachment missing filePath for document {doc_ref.ehr_resource_id}")
                        continue

                    content_type = attachment.get("contentType", "application/pdf")
                    title = attachment.get("title") or doc_ref.data.get("type", "Procedure Document")
                    file_name = attachment.get("fileName")
                    size = attachment.get("size")

                    doc_date = None
                    if doc_ref.data.get("date"):
                        try:
                            doc_date = datetime.fromisoformat(doc_ref.data["date"].replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pass

                    content = await self.s3_client.download_document(file_path)
                    text = self.text_extractor.extract_text(content, content_type, file_name or file_path)

                    extracted_documents.append(
                        DocumentAttachment(
                            file_path=file_path,
                            content_type=content_type,
                            title=title,
                            date=doc_date,
                            document_type=doc_ref.data.get("type"),
                            file_name=file_name,
                            size=size,
                            extracted_text=text,
                            extraction_error=None,
                        )
                    )

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.logger.error(
                        f"Failed to process procedure attachment: {file_path} - {error_msg}",
                        exc_info=True,
                    )
                    extracted_documents.append(
                        DocumentAttachment(
                            file_path=file_path or "unknown",
                            content_type=attachment.get("contentType", "unknown"),
                            title=attachment.get("title", "Unknown Procedure Document"),
                            date=None,
                            document_type=doc_ref.data.get("type"),
                            file_name=attachment.get("fileName"),
                            size=attachment.get("size"),
                            extracted_text="",
                            extraction_error=error_msg,
                        )
                    )

        return extracted_documents
