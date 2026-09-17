"""Attachment Summarization Service - Handles document attachment analysis and clinical insights."""

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select, cast, String
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
    AttachmentSummarizationResponse,
)
from src.app.models.conversation_summaries import ConversationSummary
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
from src.app.utils.s3_client import S3DocumentClient

from src.app.services.summary_outcomes import MESSAGES, outcome_metadata, source_manifest

from src.app.services.summary_runtime import bounded_summary

logger = get_logger(__name__)


def _static_fallback_summary_data(
    request: AttachmentSummarizationRequest,
    appointment: Appointment,
    provider_name: str,
) -> Dict[str, Any]:
    """Build the summary payload for an appointment with no document attachments to analyze.

    Pure function — no I/O — so it is directly testable without DB/network mocking.
    """
    appt_date = (
        appointment.appointment_date.strftime("%B %d, %Y")
        if appointment.appointment_date
        else None
    )
    purpose = appointment.purpose
    if provider_name and provider_name != "N/A":
        if appt_date:
            base = f"Your appointment with {provider_name} on {appt_date}"
        else:
            base = f"Your appointment with {provider_name}"
    else:
        if appt_date:
            base = f"Your appointment on {appt_date}"
        else:
            base = "Your appointment"
    if purpose:
        base += f" was for {purpose}."
    else:
        base += "."
    fallback_summary_text = (
        f"{base} No clinical documents were available for this encounter."
    )
    return {
        "summary_text": MESSAGES["no_documents"],
        "user_id": request.user_id,
        "created_by": request.user_id,
        "updated_by": request.user_id,
        "key_points": [],
        "medications": [],
        "diagnoses": [],
        "instructions": [],
        "recommendations": [],
        "data": {},
        "summary_metadata": {
            "source": "attachment_summary",
            "analysis_version": "1.0",
            **outcome_metadata("no_documents"),
            "total_documents": 0,
            "successful_documents": 0,
            "failed_documents": 0,
            "document_metadata": [],
            "extraction_errors": [],
            "encounter_id": appointment.ehr_entity_id,
            "provider_name": provider_name,
            "appointment_date": (
                appointment.appointment_date.isoformat()
                if appointment.appointment_date
                else None
            ),
            "lab_results": [],
            "risk_factors": [],
        },
    }


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
        from src.app.core.settings import get_settings
        settings = get_settings()
        self.text_extractor = DocumentTextExtractor()
        self.logger = logger

    @bounded_summary
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
        try:
            doc_references = await self._fetch_document_references(request, appointment)
        except Exception:
            await self.db.rollback()
            payload = _static_fallback_summary_data(request, appointment, provider_name)
            payload["summary_text"] = MESSAGES["unavailable"]
            payload["summary_metadata"].update(outcome_metadata("unavailable", [{"error": "SOURCE_INVENTORY_FAILED"}]))
            payload["summary_metadata"].update(total_documents=None, successful_documents=None, failed_documents=None)
            saved = await self.summaries_repo.upsert(request.appointment_id, payload)
            return ConversationSummary.model_validate(saved)

        initial_manifest = source_manifest(doc_references)
        eligibility_snapshot = self._inventory_context()

        if not doc_references:
            self.logger.info(
                f"No document attachments found for appointment {request.appointment_id} - returning static appointment summary"
            )
            summary_data = _static_fallback_summary_data(
                request, appointment, provider_name
            )
            summary_data["summary_metadata"].update(eligibility_snapshot)
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
        if eligibility_snapshot:
            appointment_context["document_eligibility"] = eligibility_snapshot

        # Reuse only after downloading/parsing current bytes and checking ownership,
        # complete validation, source membership, prompts and processing versions.
        from src.app.services.summary_cache import attachment_fingerprint, verified_attachment_cache
        fingerprint = None
        if all(d.content_sha256 and not d.extraction_error for d in extracted_documents):
            from src.app.core.settings import get_settings
            fingerprint = attachment_fingerprint(extracted_documents, initial_manifest, appointment_context, get_settings())
        cached = await verified_attachment_cache(self.summaries_repo, request, fingerprint)
        if cached is not None:
            current_references = await self._fetch_document_references(request, appointment)
            if source_manifest(current_references) != initial_manifest or self._inventory_context() != eligibility_snapshot:
                raise DocumentProcessingError("SOURCE_MANIFEST_CHANGED")
            await self.s3_client.validate_download_versions()
            return cached

        # Run AI analysis
        try:
            analysis_result = await self._run_ai_analysis(appointment_context, extracted_documents)
            from src.app.services.validated_summary import require_validated_summary
            if analysis_result.documents_analyzed:
                require_validated_summary(analysis_result)
            current_references = await self._fetch_document_references(request, appointment)
            if source_manifest(current_references) != initial_manifest or self._inventory_context() != eligibility_snapshot:
                raise DocumentProcessingError("SOURCE_MANIFEST_CHANGED")
            await self.s3_client.validate_download_versions()
        except Exception as exc:
            analysis_result = AttachmentSummarizationResponse(
                clinical_summary=MESSAGES["unavailable"], documents_analyzed=0,
                extraction_errors=[{"error": getattr(exc, "code", "SUMMARY_GENERATION_FAILED")}],
            )

        # Store analysis in database
        summary_data = self._prepare_summary_data(
            request,
            appointment,
            provider_name,
            analysis_result,
            extracted_documents,
        )

        summary_data["summary_metadata"].update(eligibility_snapshot)
        if fingerprint and summary_data["summary_metadata"]["processing_outcome"] == "complete":
            summary_data["summary_metadata"]["source_fingerprint"] = fingerprint
        db_summary = await self.summaries_repo.upsert(appointment_id=request.appointment_id, summary_data=summary_data)

        self.logger.info(
            f"Attachment summarization completed - "
            f"appointment_id: {request.appointment_id}, summary_id: {db_summary.id}, "
            f"documents_processed: {len(extracted_documents)}"
        )

        return ConversationSummary.model_validate(db_summary)

    def _inventory_context(self):
        from copy import deepcopy
        repository = getattr(self, "fhir_repo", None)
        context = {}
        if getattr(repository, "eligibility_provenance", None) is not None:
            context["document_rule_provenance"] = deepcopy(repository.eligibility_provenance)
        if getattr(repository, "document_inventory", None) is not None:
            context["document_inventory"] = deepcopy(repository.document_inventory)
        return context

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
        appointment_stmt = select(Appointment).where(Appointment.id == request.appointment_id, cast(Appointment.user_id, String) == str(request.user_id))
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

        # Soft preference (not a hard filter): prefer documents the AI type-inference
        # classifier flagged `includeForSummary=True` (clinically substantive — visit/
        # progress/consult/discharge notes, lab/imaging/pathology/operative reports)
        # when at least one exists for this encounter. Fall back to the full unfiltered
        # set when none are flagged true (field absent/null/false for every doc) — ~15%
        # of visits (telephone/imaging-only encounters) have no flagged document at all,
        # so a hard restrict would leave them with nothing. See care-capture-nodeapi's
        # 2026-09-17 document-scope-question research report, recommendation #2.
        flagged = [
            doc for doc in doc_references
            if isinstance(doc.data, dict) and doc.data.get("includeForSummary") is True
        ]
        if flagged:
            doc_references = flagged

        self.logger.debug(
            f"Fetched {len(doc_references)} DocumentReferences with attachments - "
            f"appointment_id: {request.appointment_id}"
        )

        return doc_references

    async def _process_attachments(self, doc_references: List[Any]) -> List[DocumentAttachment]:
        from src.app.services.document_ingestion import process_attachments
        return await process_attachments(doc_references, self.s3_client, self.text_extractor)

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
            self.logger.error("AI analysis failed; error_type=%s", type(e).__name__)
            raise

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
        if analysis_result.documents_analyzed:
            from src.app.services.validated_summary import require_validated_summary
            require_validated_summary(analysis_result)
        else:
            # Failed output is never a source of clinical fields.
            analysis_result = AttachmentSummarizationResponse(clinical_summary="", documents_analyzed=0, extraction_errors=analysis_result.extraction_errors)

        # Build document metadata list
        document_metadata = []
        extraction_errors = []

        for doc in extracted_documents:
            metadata = {
                "title": doc.title,
                "type": doc.content_type,
                "file_name": doc.file_name,
                "size": doc.size,
                "date": doc.date.isoformat() if doc.date else None,
                "clinical_document_type": doc.document_type,
                "source_id": doc.resource_id,
                "content_sha256": doc.content_sha256,
                "parsed_text_sha256": doc.parsed_text_sha256,
                "parser_version": doc.parser_version,
            }
            document_metadata.append(metadata)

            if doc.extraction_error:
                extraction_errors.append({"source_id": doc.resource_id or "unknown", "error": doc.extraction_error})

        extraction_errors.extend(analysis_result.extraction_errors)
        # A failed source can be reported by both ingestion and the chain. Keep
        # one record per source/code and count documents, not error events.
        extraction_errors = list({(error.get("source_id", ""), error.get("error", "INTERNAL_PROCESSING_ERROR")): error for error in extraction_errors}.values())
        failed_ids = {error.get("source_id", "").rsplit(":chunk:", 1)[0] for error in extraction_errors if error.get("source_id")}
        successful_docs = analysis_result.documents_analyzed
        state = "unavailable" if not successful_docs else "partial" if extraction_errors else "complete"
        summary_text = analysis_result.clinical_summary
        if state == "partial":
            summary_text = MESSAGES["partial"] + "\n\n" + summary_text
        elif state == "unavailable":
            from src.app.services.summary_outcomes import unavailable_message
            summary_text = unavailable_message(extraction_errors)

        return {
            "summary_text": summary_text,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": analysis_result.key_insights,
            "medications": [{"name": med} for med in analysis_result.medications_mentioned],
            "diagnoses": [d.model_dump() for d in analysis_result.diagnoses_mentioned],
            "instructions": analysis_result.instructions,
            "recommendations": [{"recommendation": rec} for rec in analysis_result.recommendations],
            "data": {
                "procedures_mentioned": analysis_result.procedures_mentioned,
                "follow_up": analysis_result.follow_up,
            },
            "summary_metadata": {
                "source": "attachment_summary",
                "analysis_version": "3.0",
                **outcome_metadata(state, extraction_errors),
                "total_documents": len(extracted_documents),
                "successful_documents": max(0, len(extracted_documents) - len(failed_ids)) if successful_docs else 0,
                "documents_with_accepted_content": successful_docs,
                "failed_documents": len(failed_ids) if successful_docs else len(extracted_documents),
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
