# Encounter Clinical Data Query - Implementation Comparison

## Overview

This document compares the encounter clinical data fetching implementation between the Node.js (TypeScript) and FastAPI (Python) projects.

Both implementations fetch:

1. The Encounter resource itself
2. All clinical resources (Observations, Conditions, Procedures, etc.) that reference this encounter via `data->>'encounterReference'`

---

## Node.js Implementation

**File:** `care-capture-nodeapi/src/modules/fhir-resources/services/encounter-clinical-data.service.ts`

### Main Method: `getEncounterWithClinicalData`

```typescript
async getEncounterWithClinicalData(
  userId: string,
  encounterId: string,
): Promise<EncounterSummary | null> {
  // Normalize encounterId - remove "Encounter/" prefix if present
  const normalizedEncounterId = encounterId.replace(/^Encounter\//, '');

  // Find the encounter
  const encounter = await this.fhirResourceRepository.findOne({
    where: {
      userId,
      resourceType: FhirResourceType.ENCOUNTER,
      ehrResourceId: normalizedEncounterId,
    },
  });

  if (!encounter) {
    return null;
  }

  // Find all clinical resources linked to this encounter
  const encounterReference = `Encounter/${normalizedEncounterId}`;

  const observations = await this.findResourcesByEncounterReference(
    userId,
    FhirResourceType.OBSERVATION,
    encounterReference,
  );

  const conditions = await this.findResourcesByEncounterReference(
    userId,
    FhirResourceType.CONDITION,
    encounterReference,
  );

  // ... similar calls for procedures, medicationRequests, diagnosticReports, documentReferences

  return {
    encounter,
    observations,
    conditions,
    procedures,
    medicationRequests,
    diagnosticReports,
    documentReferences,
    totalClinicalResources,
    resourceCounts,
  };
}
```

### Helper Method: Query by Encounter Reference

```typescript
private async findResourcesByEncounterReference(
  userId: string,
  resourceType: FhirResourceType,
  encounterReference: string,
): Promise<FhirResourceEntity[]> {
  return this.fhirResourceRepository
    .createQueryBuilder('fhir')
    .where('fhir.userId = :userId', { userId })
    .andWhere('fhir.resourceType = :resourceType', { resourceType })
    .andWhere("fhir.data->>'encounterReference' = :encounterReference", {
      encounterReference,
    })
    .orderBy('fhir.lastSyncedAt', 'DESC')
    .getMany();
}
```

### Key SQL Query Pattern (TypeORM)

```sql
SELECT * FROM fhir_resources
WHERE user_id = :userId
  AND resource_type = :resourceType
  AND data->>'encounterReference' = 'Encounter/97953483'
ORDER BY last_synced_at DESC;
```

---

## FastAPI Implementation

**File:** `/home/nithin/Project/care-capture-fastapi/src/app/db/objects/repositories/fhir_resources.py`

### Main Method: `get_encounter_with_clinical_data`

```python
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
    """
    # Normalize encounter ID - remove "Encounter/" prefix if present
    normalized_id = encounter_id.replace("Encounter/", "")
    encounter_reference = f"Encounter/{normalized_id}"

    # Build query with two conditions:
    # 1. The Encounter resource itself (resource_type = 'Encounter' AND ehr_resource_id = encounter_id)
    # 2. Resources that reference this encounter (data->>'encounterReference' = 'Encounter/{id}')
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
    return result.scalars().all()
```

### Additional Method: Get Resource Counts

```python
async def get_resource_counts_by_encounter(
    self,
    user_id: str,
    encounter_id: str
) -> dict[str, int]:
    """
    Get count of each resource type linked to a specific encounter.
    """
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
```

### Key SQL Query Pattern (SQLAlchemy)

```sql
SELECT * FROM fhir_resources
WHERE user_id = :user_id
  AND (
    -- The encounter resource itself
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    -- Resources that reference this encounter
    (data->>'encounterReference' = 'Encounter/97953483')
  )
ORDER BY last_synced_at DESC;
```

---

## Key Differences

### 1. **Query Strategy**

**Node.js:**

- Makes separate queries for each resource type
- Fetches Encounter first, then makes 6+ separate queries for each clinical resource type
- Returns structured object with resources grouped by type

**FastAPI:**

- Makes a single query using `OR` condition
- Fetches Encounter and all clinical resources in one query
- Returns flat list of resources (caller groups by type if needed)

### 2. **Return Format**

**Node.js:**

```typescript
{
  encounter: FhirResourceEntity,
  observations: FhirResourceEntity[],
  conditions: FhirResourceEntity[],
  procedures: FhirResourceEntity[],
  medicationRequests: FhirResourceEntity[],
  diagnosticReports: FhirResourceEntity[],
  documentReferences: FhirResourceEntity[],
  totalClinicalResources: number,
  resourceCounts: {
    observations: number,
    conditions: number,
    ...
  }
}
```

**FastAPI:**

```python
# Returns flat list
[
  FhirResource(resource_type='Encounter', ...),
  FhirResource(resource_type='Observation', ...),
  FhirResource(resource_type='Condition', ...),
  ...
]

# Caller groups if needed:
by_type = {}
for resource in resources:
    if resource.resource_type not in by_type:
        by_type[resource.resource_type] = []
    by_type[resource.resource_type].append(resource)
```

### 3. **Resource Filtering**

**Node.js:**

- Hard-coded resource types (6 specific types)
- Always fetches the same set of types

**FastAPI:**

- Supports optional `resource_types` parameter
- Can filter to specific types if needed
- More flexible for different use cases

### 4. **Performance**

**Node.js:**

- Multiple database round-trips (7+ queries)
- More network overhead
- Resources pre-grouped (no post-processing needed)

**FastAPI:**

- Single database query
- Less network overhead
- Requires post-processing to group by type
- More efficient for large datasets

---

## Test Results

**Test Encounter:** `97953483` (Encounter with most clinical data)

**User ID:** `abd7741f-35f1-4cc1-8d57-471921171c04`

### Results

```
✓ Total resources found: 352
  - Encounter: 1
  - Condition: 171
  - DocumentReference: 96
  - Observation: 67
  - CarePlan: 9
  - DiagnosticReport: 8

✓ Clinical resources only: 351

✓ Encounter ID normalization works correctly
  - "97953483" → 352 resources
  - "Encounter/97953483" → 352 resources

✓ Resource type filtering works correctly
  - Filter: ['Observation', 'Condition'] → 238 resources
    - Condition: 171
    - Observation: 67
```

---

## SQL Examples

### Raw SQL - Get Encounter with All Clinical Data

```sql
-- PostgreSQL query that both implementations use under the hood
SELECT
  id,
  user_id,
  resource_type,
  ehr_resource_id,
  data,
  last_synced_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND (
    -- The encounter itself
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    -- Clinical resources that reference this encounter
    (data->>'encounterReference' = 'Encounter/97953483')
  )
ORDER BY last_synced_at DESC;
```

### Get Resource Counts by Encounter

```sql
SELECT
  resource_type::text,
  COUNT(*) as count
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND data->>'encounterReference' = 'Encounter/97953483'
GROUP BY resource_type::text
ORDER BY count DESC;
```

### Find Encounters with Most Clinical Data

```sql
SELECT
  data->>'encounterReference' as encounter_ref,
  COUNT(*) as linked_resources
FROM fhir_resources
WHERE data->>'encounterReference' IS NOT NULL
GROUP BY data->>'encounterReference'
ORDER BY linked_resources DESC
LIMIT 10;
```

---

## Usage Example - FastAPI Route

**File:** `/home/nithin/Project/care-capture-fastapi/src/app/routes/care_capture.py`

```python
@router.post("/analyze_fhir")
async def analyze_fhir(
    request: FhirAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    # Initialize repository
    fhir_repo = FhirResourcesRepository(db)

    # Fetch encounter with all clinical data
    fhir_resources = await fhir_repo.get_encounter_with_clinical_data(
        user_id=str(request.user_id),
        encounter_id=appointment.ehr_entity_id,
        resource_types=request.resource_types  # Optional filter
    )

    # Get resource counts
    resource_counts = await fhir_repo.get_resource_counts_by_encounter(
        user_id=str(request.user_id),
        encounter_id=appointment.ehr_entity_id
    )

    # Group resources by type
    by_type = {}
    for resource in fhir_resources:
        if resource.resource_type not in by_type:
            by_type[resource.resource_type] = []
        by_type[resource.resource_type].append(resource.data)

    # Process and return...
```

---

## Conclusion

Both implementations achieve the same goal but with different strategies:

- **Node.js**: More queries, pre-grouped results, harder to filter
- **FastAPI**: Single query, flat results, more flexible filtering

The FastAPI implementation is more efficient for large datasets and provides better flexibility through optional resource type filtering.

**Test Status:** ✅ All tests passing - Implementation verified against production database.
