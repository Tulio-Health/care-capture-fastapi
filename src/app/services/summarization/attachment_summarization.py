"""Attachment Summarization Service - Handles document attachment analysis and clinical insights."""

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
from src.app.common.logging import get_logger
from src.app.db.models.appointments import Appointment
from src.app.db.models.ref_cms_provider_data import RefCmsProviderData
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository
from src.app.models.attachment_summarization import (
    AttachmentSummarizationRequest,
    DocumentAttachment,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.services.document_extraction import DocumentTextExtractor
from src.app.utils.s3_client import S3DocumentClient

logger = get_logger(__name__)


class AttachmentSummarizationService:
    """
    Service for analyzing document attachments and generating clinical insights.

    This service handles the business logic for:
    - Fetching DocumentReference resources with attachments from an encounter
    - Downloading documents from S3
    - Extracting text from PDFs, DOCX, and TXT files
    - Analyzing extracted content using AI
    - Generating structured clinical summaries
    - Storing analysis results in the database

    Follows the same architectural pattern as FhirAnalysisService.
    """

    # Maximum documents to process per encounter
    MAX_DOCUMENTS = 20

    def __init__(self, db: AsyncSession):
        """
        Initialize the attachment summarization service.

        Args:
            db: Database session for repository operations
        """
        self.db = db
        self.fhir_repo = FhirResourcesRepository(db)
        self.summaries_repo = ConversationSummariesRepository(db)
        self.s3_client = S3DocumentClient()
        self.text_extractor = DocumentTextExtractor()
        self.logger = logger

    async def analyze_attachments(self, request: AttachmentSummarizationRequest) -> ConversationSummary:
        """
        Analyze document attachments for a patient appointment and generate clinical insights.

        This method:
        1. Fetches appointment and provider details
        2. Retrieves DocumentReference resources with attachments for the encounter
        3. Downloads documents from S3 and extracts text
        4. Analyzes documents using AI
        5. Stores analysis in database

        Args:
            request: Contains appointment_id, user_id, and optional encounter_id

        Returns:
            ConversationSummary: Clinical insights stored in the database

        Raises:
            ValueError: If appointment or attachments not found
            Exception: If analysis or database operations fail
        """
        self.logger.info(
            f"Starting attachment summarization - appointment_id: {request.appointment_id}, user_id: {request.user_id}"
        )

        # Fetch appointment and provider details
        appointment, provider_name = await self._fetch_appointment_details(request)

        # Fetch DocumentReference resources with attachments
        doc_references = await self._fetch_document_references(request, appointment)

        if not doc_references:
            self.logger.info(
                f"No document attachments found for appointment {request.appointment_id} - returning empty summary"
            )
            summary_data = {
                "summary_text": "No document attachments found for this appointment.",
                "user_id": request.user_id,
                "created_by": request.user_id,
                "updated_by": request.user_id,
                "key_points": [],
                "medications": [],
                "diagnoses": [],
                "instructions": [],
                "recommendations": [],
                "summary_metadata": {
                    "source": "attachment_summary",
                    "analysis_version": "1.0",
                    "total_documents": 0,
                    "successful_documents": 0,
                    "failed_documents": 0,
                    "document_metadata": [],
                    "extraction_errors": [],
                    "encounter_id": appointment.ehr_entity_id,
                    "provider_name": provider_name,
                    "appointment_date": (
                        appointment.appointment_date.isoformat() if appointment.appointment_date else None
                    ),
                    "lab_results": [],
                    "risk_factors": [],
                },
            }
            db_summary = await self.summaries_repo.upsert(
                appointment_id=request.appointment_id, summary_data=summary_data
            )
            return ConversationSummary.model_validate(db_summary)

        # Download and extract text from all attachments
        extracted_documents = await self._process_attachments(doc_references)

        if not extracted_documents:
            raise ValueError(f"Failed to extract text from any attachments for appointment {request.appointment_id}")

        # Build appointment context
        appointment_context = self._build_appointment_context(appointment, provider_name)

        # Run AI analysis
        analysis_result = await self._run_ai_analysis(appointment_context, extracted_documents)

        # Store analysis in database
        summary_data = self._prepare_summary_data(
            request,
            appointment,
            provider_name,
            analysis_result,
            extracted_documents,
        )

        db_summary = await self.summaries_repo.upsert(appointment_id=request.appointment_id, summary_data=summary_data)

        self.logger.info(
            f"Attachment summarization completed - "
            f"appointment_id: {request.appointment_id}, summary_id: {db_summary.id}, "
            f"documents_processed: {len(extracted_documents)}"
        )

        return ConversationSummary.model_validate(db_summary)

    async def _fetch_appointment_details(self, request: AttachmentSummarizationRequest) -> tuple[Appointment, str]:
        """
        Fetch appointment and provider details.

        Args:
            request: Attachment summarization request

        Returns:
            tuple: (Appointment object, provider name)

        Raises:
            ValueError: If appointment not found
        """
        # Fetch appointment
        appointment_stmt = select(Appointment).where(Appointment.id == request.appointment_id)
        appointment_result = await self.db.execute(appointment_stmt)
        appointment = appointment_result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {request.appointment_id} not found")

        # Fetch provider details
        provider_name = "N/A"
        if appointment.provider_id:
            provider_stmt = select(RefCmsProviderData).where(RefCmsProviderData.id == appointment.provider_id)
            provider_result = await self.db.execute(provider_stmt)
            provider = provider_result.scalar_one_or_none()
            if provider:
                provider_name = f"{provider.provider_first_name} {provider.provider_last_name}"

        self.logger.debug(
            f"Fetched appointment details - appointment_id: {request.appointment_id}, provider: {provider_name}"
        )

        return appointment, provider_name

    async def _fetch_document_references(
        self, request: AttachmentSummarizationRequest, appointment: Appointment
    ) -> List[Any]:
        """
        Fetch DocumentReference resources with attachments for the encounter.

        Args:
            request: Attachment summarization request
            appointment: Appointment object

        Returns:
            List of FhirResource objects (DocumentReferences)

        Raises:
            ValueError: If no documents with attachments found or appointment has no EHR entity ID
        """
        if not appointment.ehr_entity_id:
            raise ValueError(
                f"Appointment {request.appointment_id} has no EHR entity ID - cannot fetch document attachments"
            )

        doc_references = await self.fhir_repo.get_document_references_with_attachments(
            user_id=str(request.user_id),
            encounter_id=appointment.ehr_entity_id,
        )

        # Limit documents to prevent overwhelming the AI
        if len(doc_references) > self.MAX_DOCUMENTS:
            self.logger.warning(f"Found {len(doc_references)} documents, limiting to {self.MAX_DOCUMENTS}")
            doc_references = doc_references[: self.MAX_DOCUMENTS]

        self.logger.debug(
            f"Fetched {len(doc_references)} DocumentReferences with attachments - "
            f"appointment_id: {request.appointment_id}"
        )

        return doc_references

    async def _process_attachments(self, doc_references: List[Any]) -> List[DocumentAttachment]:
        """
        Download and extract text from all attachments.

        Handles partial failures gracefully - continues processing other documents
        if some fail to download or extract.

        Args:
            doc_references: List of FhirResource objects (DocumentReferences)

        Returns:
            List of DocumentAttachment objects with extracted text
        """
        extracted_documents = []

        for doc_ref in doc_references:
            attachments_data = doc_ref.data.get("attachments")
            if not attachments_data:
                continue

            # Handle both array and single object (defensive)
            attachments = attachments_data if isinstance(attachments_data, list) else [attachments_data]

            for attachment in attachments:
                try:
                    # Skip attachments that weren't successfully downloaded
                    if attachment.get("downloadStatus") != "success":
                        self.logger.debug(f"Skipping attachment with status '{attachment.get('downloadStatus')}' for document {doc_ref.ehr_resource_id}")
                        continue

                    # Extract attachment metadata
                    file_path = attachment.get("filePath")
                    if not file_path:
                        self.logger.warning(f"Attachment missing filePath for document {doc_ref.ehr_resource_id}")
                        continue

                    content_type = attachment.get("contentType", "application/pdf")
                    title = attachment.get("title") or doc_ref.data.get("type", "Document")
                    file_name = attachment.get("fileName")
                    size = attachment.get("size")

                    # Parse document date
                    doc_date = None
                    if doc_ref.data.get("date"):
                        try:
                            doc_date = datetime.fromisoformat(doc_ref.data["date"].replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pass

                    self.logger.info(
                        f"Processing attachment: {file_name or file_path} (type: {content_type}, size: {size})"
                    )

                    # Download from S3
                    content = await self.s3_client.download_document(file_path)

                    # Verify content type against file extension if mismatch
                    if content_type and file_path:
                        inferred_type = self.s3_client.get_content_type_from_path(file_path)
                        if inferred_type != content_type:
                            self.logger.warning(
                                f"Content type mismatch - declared: {content_type}, "
                                f"inferred: {inferred_type}. Using declared type."
                            )

                    # Extract text
                    text = self.text_extractor.extract_text(content, content_type, file_name or file_path)

                    extracted_documents.append(
                        DocumentAttachment(
                            file_path=file_path,
                            content_type=content_type,
                            title=title,
                            date=doc_date,
                            file_name=file_name,
                            size=size,
                            extracted_text=text,
                            extraction_error=None,
                        )
                    )

                    self.logger.info(f"Successfully extracted {len(text)} characters from {file_name or file_path}")

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.logger.error(
                        f"Failed to process attachment: {file_path} - {error_msg}",
                        exc_info=True,
                    )

                    # Include partial result with error metadata for tracking
                    extracted_documents.append(
                        DocumentAttachment(
                            file_path=file_path,
                            content_type=attachment.get("contentType", "unknown"),
                            title=attachment.get("title", "Unknown Document"),
                            date=None,
                            file_name=attachment.get("fileName"),
                            size=attachment.get("size"),
                            extracted_text="",
                            extraction_error=error_msg,
                        )
                    )

        successful_count = sum(1 for doc in extracted_documents if not doc.extraction_error)
        failed_count = len(extracted_documents) - successful_count

        self.logger.info(f"Attachment processing complete - successful: {successful_count}, failed: {failed_count}")

        return extracted_documents

    def _format_documents_for_prompt(self, extracted_documents: List[DocumentAttachment]) -> str:
        """
        Format extracted documents for AI prompt.

        Orders documents by date (oldest → newest) and formats with metadata.

        Args:
            extracted_documents: List of DocumentAttachment objects

        Returns:
            Formatted text with document metadata and content
        """
        # Filter out documents with extraction errors
        valid_documents = [doc for doc in extracted_documents if not doc.extraction_error]

        if not valid_documents:
            return "No documents successfully extracted."

        # Sort by date (oldest first for chronological narrative)
        valid_documents.sort(key=lambda doc: doc.date or datetime.min)

        formatted_parts = []

        for idx, doc in enumerate(valid_documents, 1):
            doc_header = f"\n{'=' * 80}\n"
            doc_header += f"DOCUMENT {idx} of {len(valid_documents)}\n"
            doc_header += f"Title: {doc.title}\n"
            if doc.date:
                doc_header += f"Date: {doc.date.strftime('%Y-%m-%d')}\n"
            doc_header += f"Type: {doc.content_type}\n"
            if doc.file_name:
                doc_header += f"Filename: {doc.file_name}\n"
            doc_header += f"{'=' * 80}\n\n"

            doc_content = doc.extracted_text[:10000]  # Limit to 10K chars per doc
            if len(doc.extracted_text) > 10000:
                doc_content += f"\n\n[... truncated, total length: {len(doc.extracted_text)} characters]"

            formatted_parts.append(doc_header + doc_content)

        return "\n\n".join(formatted_parts)

    def _build_appointment_context(self, appointment: Appointment, provider_name: str) -> Dict[str, str]:
        """
        Build appointment context for AI analysis.

        Args:
            appointment: Appointment object
            provider_name: Name of the provider

        Returns:
            Dictionary with appointment context
        """
        return {
            "appointment_date": (appointment.appointment_date.isoformat() if appointment.appointment_date else "N/A"),
            "purpose": appointment.purpose or "N/A",
            "provider_name": provider_name,
        }

    async def _run_ai_analysis(
        self,
        appointment_context: Dict[str, str],
        extracted_documents: List[DocumentAttachment],
    ) -> Any:
        """
        Run AI analysis on extracted documents using the map-reduce pipeline.

        Args:
            appointment_context: Context about the appointment
            extracted_documents: List of DocumentAttachment objects

        Returns:
            Analysis result object

        Raises:
            Exception: If AI analysis fails
        """
        try:
            analysis_chain = AttachmentSummarizationChain()
            analysis_result = await analysis_chain.analyze(
                appointment_context=appointment_context,
                documents=extracted_documents,
            )

            self.logger.debug("AI analysis completed successfully")
            return analysis_result

        except Exception as e:
            self.logger.error(f"AI analysis failed: {str(e)}", exc_info=True)
            raise Exception(f"AI analysis failed: {str(e)}")

    def _prepare_summary_data(
        self,
        request: AttachmentSummarizationRequest,
        appointment: Appointment,
        provider_name: str,
        analysis_result: Any,
        extracted_documents: List[DocumentAttachment],
    ) -> Dict[str, Any]:
        """
        Prepare summary data for database storage.

        Args:
            request: Original request
            appointment: Appointment object
            provider_name: Name of provider
            analysis_result: AI analysis result
            extracted_documents: All processed documents (including failures)

        Returns:
            Dictionary ready for database insertion
        """
        # Build document metadata list
        document_metadata = []
        extraction_errors = []

        # Build lookup from title to LLM-inferred clinical document type
        llm_type_by_title = {
            m.get("title", ""): m.get("type")
            for m in (analysis_result.document_metadata or [])
        }

        for doc in extracted_documents:
            metadata = {
                "title": doc.title,
                "type": doc.content_type,
                "file_name": doc.file_name,
                "size": doc.size,
                "date": doc.date.isoformat() if doc.date else None,
                "clinical_document_type": llm_type_by_title.get(doc.title),
            }
            document_metadata.append(metadata)

            if doc.extraction_error:
                extraction_errors.append({"file_path": doc.file_path, "error": doc.extraction_error})

        successful_docs = len([d for d in extracted_documents if not d.extraction_error])

        return {
            "summary_text": analysis_result.clinical_summary,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": analysis_result.key_insights,
            "medications": [{"name": med} for med in analysis_result.medications_mentioned],
            "diagnoses": analysis_result.diagnoses_mentioned,
            "instructions": analysis_result.instructions,
            "recommendations": [{"recommendation": rec} for rec in analysis_result.recommendations],
            "summary_metadata": {
                "source": "attachment_summary",
                "analysis_version": "2.0",
                "total_documents": len(extracted_documents),
                "successful_documents": successful_docs,
                "failed_documents": len(extraction_errors),
                "document_metadata": document_metadata,
                "extraction_errors": extraction_errors,
                "encounter_id": appointment.ehr_entity_id,
                "provider_name": provider_name,
                "appointment_date": (
                    appointment.appointment_date.isoformat() if appointment.appointment_date else None
                ),
                "lab_results": analysis_result.lab_results,
                "risk_factors": analysis_result.risk_factors,
            },
        }
