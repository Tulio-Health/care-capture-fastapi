"""FHIR Analysis Service - Handles FHIR resource analysis and clinical insights."""

from typing import Dict, List, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.chains.fhir_analysis.chain import FhirAnalysisChain
from src.app.common.logging import get_logger
from src.app.db.models.appointments import Appointment
from src.app.db.models.ref_cms_provider_data import RefCmsProviderData
from src.app.db.objects.repositories.conversation_summaries import (
    ConversationSummariesRepository,
)
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository
from src.app.models.conversation_summaries import ConversationSummary
from src.app.models.fhir_analysis import FhirAnalysisRequest

logger = get_logger(__name__)


class FhirAnalysisService:
    """
    Service for analyzing FHIR resources and generating clinical insights.
    
    This service handles the business logic for:
    - Fetching FHIR resources for specific appointments/encounters
    - Analyzing clinical data using AI
    - Generating structured clinical summaries
    - Storing analysis results in the database
    """

    # Limit records per resource type to avoid context overflow
    MAX_RECORDS_PER_TYPE = 10
    MAX_STORED_ITEMS = 20

    def __init__(self, db: AsyncSession):
        """
        Initialize the FHIR analysis service.
        
        Args:
            db: Database session for repository operations
        """
        self.db = db
        self.fhir_repo = FhirResourcesRepository(db)
        self.summaries_repo = ConversationSummariesRepository(db)
        self.logger = logger

    async def analyze_fhir_resources(
        self, request: FhirAnalysisRequest
    ) -> ConversationSummary:
        """
        Analyze FHIR resources for a patient appointment and generate clinical insights.
        
        This method:
        1. Fetches appointment and provider details
        2. Retrieves FHIR resources for the encounter
        3. Analyzes resources using AI
        4. Stores analysis in database
        
        Args:
            request: Contains appointment_id, user_id, and optional filters
        
        Returns:
            ConversationSummary: Clinical insights stored in the database
        
        Raises:
            ValueError: If appointment or FHIR resources not found
            Exception: If analysis or database operations fail
        """
        self.logger.info(
            f"Starting FHIR analysis - "
            f"appointment_id: {request.appointment_id}, user_id: {request.user_id}"
        )

        # Fetch appointment and provider details
        appointment, provider_name = await self._fetch_appointment_details(request)

        # Fetch FHIR resources
        fhir_resources = await self._fetch_fhir_resources(request, appointment)

        # Get resource counts
        resource_counts = await self._get_resource_counts(request, appointment)

        # Build FHIR summary
        fhir_summary_by_type = self._group_resources_by_type(fhir_resources)
        fhir_summary_text = self._format_fhir_summary(fhir_summary_by_type)

        # Build appointment context
        appointment_context = self._build_appointment_context(appointment, provider_name)

        # Run AI analysis
        analysis_result = await self._run_ai_analysis(
            appointment_context, fhir_summary_text, resource_counts
        )

        # Extract structured data
        conditions_list = self._extract_conditions(fhir_resources)
        medications_list = self._extract_medications(fhir_resources)

        # Store analysis in database
        summary_data = self._prepare_summary_data(
            request,
            appointment,
            provider_name,
            analysis_result,
            conditions_list,
            medications_list,
            fhir_resources,
            resource_counts,
            fhir_summary_by_type,
        )

        db_summary = await self.summaries_repo.upsert(
            appointment_id=request.appointment_id, summary_data=summary_data
        )

        self.logger.info(
            f"FHIR analysis completed - "
            f"appointment_id: {request.appointment_id}, summary_id: {db_summary.id}"
        )

        return ConversationSummary.model_validate(db_summary)

    async def _fetch_appointment_details(
        self, request: FhirAnalysisRequest
    ) -> tuple[Appointment, str]:
        """
        Fetch appointment and provider details.
        
        Args:
            request: FHIR analysis request
        
        Returns:
            tuple: (Appointment object, provider name)
        
        Raises:
            ValueError: If appointment not found
        """
        # Fetch appointment
        appointment_stmt = select(Appointment).where(
            Appointment.id == request.appointment_id
        )
        appointment_result = await self.db.execute(appointment_stmt)
        appointment = appointment_result.scalar_one_or_none()

        if not appointment:
            raise ValueError(f"Appointment {request.appointment_id} not found")

        # Fetch provider details
        provider_name = "N/A"
        if appointment.provider_id:
            provider_stmt = select(RefCmsProviderData).where(
                RefCmsProviderData.id == appointment.provider_id
            )
            provider_result = await self.db.execute(provider_stmt)
            provider = provider_result.scalar_one_or_none()
            if provider:
                provider_name = (
                    f"{provider.provider_first_name} {provider.provider_last_name}"
                )

        self.logger.debug(
            f"Fetched appointment details - "
            f"appointment_id: {request.appointment_id}, provider: {provider_name}"
        )

        return appointment, provider_name

    async def _fetch_fhir_resources(
        self, request: FhirAnalysisRequest, appointment: Appointment
    ) -> List[Any]:
        """
        Fetch FHIR resources for the appointment's encounter.
        
        Args:
            request: FHIR analysis request
            appointment: Appointment object
        
        Returns:
            List of FHIR resource objects
        
        Raises:
            ValueError: If no FHIR resources found or appointment has no EHR entity ID
        """
        if not appointment.ehr_entity_id:
            raise ValueError(
                f"Appointment {request.appointment_id} has no EHR entity ID - "
                "cannot fetch FHIR resources"
            )

        fhir_resources = await self.fhir_repo.get_encounter_with_clinical_data(
            user_id=str(request.user_id),
            encounter_id=appointment.ehr_entity_id,
            resource_types=request.resource_types,
        )

        if not fhir_resources:
            raise ValueError(
                f"No FHIR resources found for appointment {request.appointment_id} "
                f"(encounter: {appointment.ehr_entity_id})"
            )

        self.logger.debug(
            f"Fetched {len(fhir_resources)} FHIR resources - "
            f"appointment_id: {request.appointment_id}"
        )

        return fhir_resources

    async def _get_resource_counts(
        self, request: FhirAnalysisRequest, appointment: Appointment
    ) -> Dict[str, int]:
        """
        Get resource counts for the encounter.
        
        Args:
            request: FHIR analysis request
            appointment: Appointment object
        
        Returns:
            Dictionary mapping resource types to counts
        """
        resource_counts = await self.fhir_repo.get_resource_counts_by_encounter(
            user_id=str(request.user_id), encounter_id=appointment.ehr_entity_id
        )

        self.logger.debug(
            f"Resource counts: {resource_counts} - "
            f"appointment_id: {request.appointment_id}"
        )

        return resource_counts

    def _group_resources_by_type(self, fhir_resources: List[Any]) -> Dict[str, List[Dict]]:
        """
        Group FHIR resources by resource type.
        
        Args:
            fhir_resources: List of FHIR resource objects
        
        Returns:
            Dictionary mapping resource types to lists of resource data
        """
        fhir_summary_by_type = {}
        for resource in fhir_resources:
            resource_type = resource.resource_type
            if resource_type not in fhir_summary_by_type:
                fhir_summary_by_type[resource_type] = []
            fhir_summary_by_type[resource_type].append(resource.data)

        return fhir_summary_by_type

    def _format_fhir_summary(self, fhir_summary_by_type: Dict[str, List[Dict]]) -> str:
        """
        Format FHIR summary for AI prompt.
        
        Args:
            fhir_summary_by_type: Dictionary of resources grouped by type
        
        Returns:
            Formatted text summary of FHIR resources
        """
        fhir_summary_text = ""

        for resource_type, resources in fhir_summary_by_type.items():
            fhir_summary_text += f"\n**{resource_type}** ({len(resources)} records):\n"

            # Limit to first MAX_RECORDS_PER_TYPE to avoid context overflow
            for idx, resource_data in enumerate(resources[: self.MAX_RECORDS_PER_TYPE]):
                # Extract key fields based on resource type
                if resource_type == "Condition":
                    code_text = resource_data.get("codeText", "N/A")
                    category = (
                        resource_data.get("categoryText", ["N/A"])[0]
                        if resource_data.get("categoryText")
                        else "N/A"
                    )
                    fhir_summary_text += f"  {idx + 1}. {code_text} ({category})\n"
                elif resource_type == "Observation":
                    code_text = resource_data.get("codeText", "N/A")
                    value = resource_data.get("valueQuantity", {}).get("value", "N/A")
                    unit = resource_data.get("valueQuantity", {}).get("unit", "")
                    fhir_summary_text += f"  {idx + 1}. {code_text}: {value} {unit}\n"
                elif resource_type == "MedicationRequest":
                    medication = resource_data.get("medicationCodeText", "N/A")
                    status = resource_data.get("status", "N/A")
                    fhir_summary_text += f"  {idx + 1}. {medication} (Status: {status})\n"
                else:
                    # Generic summary for other types
                    metadata = resource_data.get("metadata", {})
                    fhir_summary_text += (
                        f"  {idx + 1}. {metadata.get('resourceType', resource_type)}\n"
                    )

            if len(resources) > self.MAX_RECORDS_PER_TYPE:
                fhir_summary_text += (
                    f"  ... and {len(resources) - self.MAX_RECORDS_PER_TYPE} more records\n"
                )

        return fhir_summary_text

    def _build_appointment_context(
        self, appointment: Appointment, provider_name: str
    ) -> Dict[str, str]:
        """
        Build appointment context for AI analysis.
        
        Args:
            appointment: Appointment object
            provider_name: Name of the provider
        
        Returns:
            Dictionary with appointment context
        """
        return {
            "appointment_date": (
                appointment.appointment_date.isoformat()
                if appointment.appointment_date
                else "N/A"
            ),
            "purpose": appointment.purpose or "N/A",
            "provider_name": provider_name,
        }

    async def _run_ai_analysis(
        self,
        appointment_context: Dict[str, str],
        fhir_summary: str,
        resource_counts: Dict[str, int],
    ) -> Any:
        """
        Run AI analysis on FHIR resources.
        
        Args:
            appointment_context: Context about the appointment
            fhir_summary: Formatted FHIR summary text
            resource_counts: Resource counts by type
        
        Returns:
            Analysis result object
        
        Raises:
            Exception: If AI analysis fails
        """
        try:
            analysis_chain = FhirAnalysisChain()
            analysis_result = analysis_chain.analyze(
                appointment_context=appointment_context,
                fhir_summary=fhir_summary,
                resource_counts=resource_counts,
            )

            self.logger.debug("AI analysis completed successfully")
            return analysis_result

        except Exception as e:
            self.logger.error(f"AI analysis failed: {str(e)}", exc_info=True)
            raise Exception(f"AI analysis failed: {str(e)}")

    def _extract_conditions(self, fhir_resources: List[Any]) -> List[str]:
        """
        Extract condition names from FHIR resources.
        
        Args:
            fhir_resources: List of FHIR resource objects
        
        Returns:
            List of condition names (limited to MAX_STORED_ITEMS)
        """
        conditions = [
            resource.data.get("codeText", "Unknown")
            for resource in fhir_resources
            if resource.resource_type == "Condition"
        ][: self.MAX_STORED_ITEMS]

        return conditions

    def _extract_medications(self, fhir_resources: List[Any]) -> List[Dict[str, str]]:
        """
        Extract medication information from FHIR resources.
        
        Args:
            fhir_resources: List of FHIR resource objects
        
        Returns:
            List of medication dictionaries (limited to MAX_STORED_ITEMS)
        """
        medications = [
            {"name": resource.data.get("medicationCodeText", "Unknown")}
            for resource in fhir_resources
            if resource.resource_type == "MedicationRequest"
        ][: self.MAX_STORED_ITEMS]

        return medications

    def _prepare_summary_data(
        self,
        request: FhirAnalysisRequest,
        appointment: Appointment,
        provider_name: str,
        analysis_result: Any,
        conditions_list: List[str],
        medications_list: List[Dict[str, str]],
        fhir_resources: List[Any],
        resource_counts: Dict[str, int],
        fhir_summary_by_type: Dict[str, List[Dict]],
    ) -> Dict[str, Any]:
        """
        Prepare summary data for database storage.
        
        Args:
            request: Original request
            appointment: Appointment object
            provider_name: Name of provider
            analysis_result: AI analysis result
            conditions_list: Extracted conditions
            medications_list: Extracted medications
            fhir_resources: All FHIR resources
            resource_counts: Resource counts by type
            fhir_summary_by_type: Resources grouped by type
        
        Returns:
            Dictionary ready for database insertion
        """
        return {
            "summary_text": analysis_result.clinical_summary,
            "user_id": request.user_id,
            "created_by": request.user_id,
            "updated_by": request.user_id,
            "key_points": analysis_result.key_insights,
            "medications": medications_list,
            "diagnoses": conditions_list,
            "instructions": [],  # FHIR analysis doesn't have instructions
            "recommendations": analysis_result.recommendations,
            "summary_metadata": {
                "source": "fhir_analysis",
                "analysis_version": "1.0",
                "total_resources": len(fhir_resources),
                "resource_counts": resource_counts,
                "analysis_focus": request.analysis_focus,
                "encounter_id": appointment.ehr_entity_id,
                "resource_types_included": list(fhir_summary_by_type.keys()),
                "provider_name": provider_name,
                "appointment_date": (
                    appointment.appointment_date.isoformat()
                    if appointment.appointment_date
                    else None
                ),
            },
        }
