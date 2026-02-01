from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, cast, String
from src.app.db.models.fhir_resources import FhirResource
from src.app.common.logging import get_logger
from uuid import UUID

logger = get_logger(__name__)


class FhirResourcesRepository:
    """Repository for querying FHIR resources from the database"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(
        self, 
        user_id: str, 
        resource_types: list[str] | None = None,
        limit: int = 1000
    ) -> list[FhirResource]:
        """
        Fetch FHIR resources for a user, optionally filtered by resource types
        
        Args:
            user_id: The user's ID (Clerk ID)
            resource_types: Optional list of resource types to filter by
            limit: Maximum number of resources to return (default 1000)
            
        Returns:
            List of FhirResource objects
        """
        try:
            query = select(FhirResource).where(FhirResource.user_id == user_id)
            
            if resource_types:
                query = query.where(cast(FhirResource.resource_type, String).in_(resource_types))
            
            query = query.order_by(FhirResource.last_synced_at.desc()).limit(limit)
            
            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching FHIR resources for user {user_id}", exc_info=e)
            raise e

    async def get_by_encounter(
        self, 
        user_id: str, 
        encounter_id: str,
        resource_types: list[str] | None = None
    ) -> list[FhirResource]:
        """
        Fetch FHIR resources linked to a specific encounter.
        Uses data->>'encounterReference' which contains values like "Encounter/98052727"
        
        This matches the NodeAPI implementation which queries:
        data->>'encounterReference' = 'Encounter/{encounter_id}'
        
        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID (ehr_resource_id from Encounter FHIR resource)
            resource_types: Optional list of resource types to filter by
            
        Returns:
            List of FhirResource objects linked to this encounter via encounterReference
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"
            
            # Query using data->>'encounterReference'
            # This will find all clinical resources (Observations, Conditions, etc.) 
            # that reference this specific encounter
            query = select(FhirResource).where(
                FhirResource.user_id == user_id,
                func.jsonb_extract_path_text(FhirResource.data, 'encounterReference') == encounter_reference
            )
            
            if resource_types:
                query = query.where(cast(FhirResource.resource_type, String).in_(resource_types))
            
            query = query.order_by(FhirResource.last_synced_at.desc())
            
            result = await self.session.execute(query)
            resources = result.scalars().all()
            
            logger.info(
                f"Found {len(resources)} resources for encounter {encounter_reference} (user: {user_id[:8]}...)"
            )
            
            return resources
        except Exception as e:
            logger.error(f"Error fetching FHIR resources for encounter {encounter_id}", exc_info=e)
            raise e
    
    async def get_resource_counts_by_encounter(
        self, 
        user_id: str, 
        encounter_id: str
    ) -> dict[str, int]:
        """
        Get count of each resource type linked to a specific encounter.
        Uses data->>'encounterReference' to find linked resources.
        
        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID
            
        Returns:
            Dictionary mapping resource_type to count
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"
            
            query = (
                select(
                    FhirResource.resource_type,
                    func.count(FhirResource.id).label('count')
                )
                .where(
                    FhirResource.user_id == user_id,
                    func.jsonb_extract_path_text(FhirResource.data, 'encounterReference') == encounter_reference
                )
                .group_by(FhirResource.resource_type)
            )
            
            result = await self.session.execute(query)
            rows = result.all()
            
            return {row.resource_type: row.count for row in rows}
        except Exception as e:
            logger.error(f"Error getting resource counts for encounter {encounter_id}", exc_info=e)
            raise e

    async def get_resource_counts(self, user_id: str) -> dict[str, int]:
        """
        Get count of each resource type for a user
        
        Args:
            user_id: The user's ID (Clerk ID)
            
        Returns:
            Dictionary mapping resource_type to count
        """
        try:
            query = (
                select(
                    FhirResource.resource_type,
                    func.count(FhirResource.id).label('count')
                )
                .where(FhirResource.user_id == user_id)
                .group_by(FhirResource.resource_type)
            )
            
            result = await self.session.execute(query)
            rows = result.all()
            
            # Convert to dict, extracting string value (no longer enum)
            return {row.resource_type: row.count for row in rows}
        except Exception as e:
            logger.error(f"Error getting resource counts for user {user_id}", exc_info=e)
            raise e

    async def get_encounter_with_clinical_data(
        self, 
        user_id: str, 
        encounter_id: str,
        resource_types: list[str] | None = None
    ) -> list[FhirResource]:
        """
        Fetch encounter resource AND all clinical resources linked to it.
        This matches NodeAPI's getEncounterWithClinicalData behavior.
        
        Returns the Encounter resource itself PLUS all resources that reference it
        via data->>'encounterReference'.
        
        Args:
            user_id: The user's ID (Clerk ID)
            encounter_id: The EHR encounter ID (ehr_resource_id from Encounter FHIR resource)
            resource_types: Optional list of resource types to filter by
            
        Returns:
            List containing:
            - The Encounter resource itself (where ehr_resource_id = encounter_id)
            - All clinical resources that reference this encounter (via encounterReference)
        """
        try:
            # Normalize encounter ID - remove "Encounter/" prefix if present
            normalized_id = encounter_id.replace("Encounter/", "")
            encounter_reference = f"Encounter/{normalized_id}"
            
            # Build query with two conditions:
            # 1. The Encounter resource itself (resource_type = 'Encounter' AND ehr_resource_id = encounter_id)
            # 2. Resources that reference this encounter (data->>'encounterReference' = 'Encounter/{id}')
            # Note: Cast resource_type to String to handle PostgreSQL enum type
            query = select(FhirResource).where(
                FhirResource.user_id == user_id,
                or_(
                    # The encounter resource itself
                    (
                        (cast(FhirResource.resource_type, String) == 'Encounter') &
                        (FhirResource.ehr_resource_id == normalized_id)
                    ),
                    # Resources that reference this encounter
                    func.jsonb_extract_path_text(FhirResource.data, 'encounterReference') == encounter_reference
                )
            )
            
            if resource_types:
                query = query.where(cast(FhirResource.resource_type, String).in_(resource_types))
            
            query = query.order_by(FhirResource.last_synced_at.desc())
            
            result = await self.session.execute(query)
            resources = result.scalars().all()
            
            logger.info(
                f"Found {len(resources)} resources (including encounter) for encounter {encounter_reference} (user: {user_id[:8]}...)"
            )
            
            return resources
        except Exception as e:
            logger.error(f"Error fetching encounter with clinical data for {encounter_id}", exc_info=e)
            raise e

    async def get_by_id(self, resource_id: UUID) -> FhirResource | None:
        """
        Fetch a single FHIR resource by ID
        
        Args:
            resource_id: The FHIR resource UUID
            
        Returns:
            FhirResource object or None if not found
        """
        try:
            result = await self.session.execute(
                select(FhirResource).where(FhirResource.id == resource_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching FHIR resource {resource_id}", exc_info=e)
            raise e
