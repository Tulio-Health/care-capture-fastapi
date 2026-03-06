-- ============================================================================
-- Encounter Clinical Data Queries
-- ============================================================================
-- These queries demonstrate how to fetch encounter-related clinical data
-- from the fhir_resources table. This matches the implementation in both
-- Node.js and FastAPI projects.
--
-- Database: care-capture-app-dev (AWS RDS PostgreSQL)
-- Table: fhir_resources
-- ============================================================================

-- Test Data
-- User ID: abd7741f-35f1-4cc1-8d57-471921171c04
-- Encounter ID: 97953483 (has 352 total resources)
-- ============================================================================


-- ============================================================================
-- Query 1: Get Encounter with ALL Clinical Data
-- ============================================================================
-- This is the main query that fetches:
-- 1. The Encounter resource itself
-- 2. All clinical resources (Observations, Conditions, etc.) that reference it
-- ============================================================================

SELECT 
  id,
  user_id,
  resource_type::text,
  ehr_resource_id,
  ehr_provider::text,
  data,
  last_synced_at,
  created_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND (
    -- The encounter resource itself
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    -- Clinical resources that reference this encounter via data->>'encounterReference'
    (data->>'encounterReference' = 'Encounter/97953483')
  )
ORDER BY last_synced_at DESC;

-- Expected: 352 rows
-- Breakdown:
--   - Encounter: 1
--   - Condition: 171
--   - DocumentReference: 96
--   - Observation: 67
--   - CarePlan: 9
--   - DiagnosticReport: 8


-- ============================================================================
-- Query 2: Get Resource Counts by Encounter
-- ============================================================================
-- Count how many resources of each type are linked to an encounter
-- ============================================================================

SELECT 
  resource_type::text,
  COUNT(*) as count
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND (
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    (data->>'encounterReference' = 'Encounter/97953483')
  )
GROUP BY resource_type::text
ORDER BY count DESC;


-- ============================================================================
-- Query 3: Get ONLY Clinical Resources (exclude Encounter itself)
-- ============================================================================
-- Fetch only the clinical resources that reference the encounter
-- ============================================================================

SELECT 
  id,
  resource_type::text,
  ehr_resource_id,
  data->>'encounterReference' as encounter_reference,
  data,
  last_synced_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND data->>'encounterReference' = 'Encounter/97953483'
ORDER BY last_synced_at DESC;

-- Expected: 351 rows (all except the Encounter itself)


-- ============================================================================
-- Query 4: Filter by Specific Resource Types
-- ============================================================================
-- Get encounter and specific types of clinical data only
-- ============================================================================

SELECT 
  id,
  resource_type::text,
  ehr_resource_id,
  data,
  last_synced_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND (
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    (data->>'encounterReference' = 'Encounter/97953483')
  )
  AND resource_type::text IN ('Encounter', 'Observation', 'Condition')
ORDER BY resource_type::text, last_synced_at DESC;

-- Expected: 239 rows (1 Encounter + 67 Observations + 171 Conditions)


-- ============================================================================
-- Query 5: Find All Encounters for a User
-- ============================================================================
-- Get all encounters with their resource counts
-- ============================================================================

WITH encounter_data AS (
  SELECT 
    ehr_resource_id as encounter_id,
    data->>'status' as status,
    data->>'classCode' as class_code,
    last_synced_at
  FROM fhir_resources
  WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
    AND resource_type::text = 'Encounter'
),
resource_counts AS (
  SELECT 
    REPLACE(data->>'encounterReference', 'Encounter/', '') as encounter_id,
    resource_type::text,
    COUNT(*) as count
  FROM fhir_resources
  WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
    AND data->>'encounterReference' IS NOT NULL
  GROUP BY data->>'encounterReference', resource_type::text
)
SELECT 
  e.encounter_id,
  e.status,
  e.class_code,
  e.last_synced_at,
  COALESCE(SUM(rc.count), 0) as total_clinical_resources,
  json_object_agg(
    COALESCE(rc.resource_type, 'none'), 
    COALESCE(rc.count, 0)
  ) FILTER (WHERE rc.resource_type IS NOT NULL) as resource_counts
FROM encounter_data e
LEFT JOIN resource_counts rc ON e.encounter_id = rc.encounter_id
GROUP BY e.encounter_id, e.status, e.class_code, e.last_synced_at
ORDER BY total_clinical_resources DESC;


-- ============================================================================
-- Query 6: Find Encounters with Most Clinical Data
-- ============================================================================
-- Identify which encounters have the most linked resources
-- ============================================================================

SELECT 
  data->>'encounterReference' as encounter_reference,
  COUNT(*) as linked_resources,
  json_object_agg(resource_type::text, count) as breakdown
FROM (
  SELECT 
    data->>'encounterReference',
    resource_type::text,
    COUNT(*) as count
  FROM fhir_resources
  WHERE data->>'encounterReference' IS NOT NULL
  GROUP BY data->>'encounterReference', resource_type::text
) subquery
GROUP BY data->>'encounterReference'
ORDER BY linked_resources DESC
LIMIT 10;

-- Top encounter: Encounter/97953483 with 351 linked resources


-- ============================================================================
-- Query 7: Get Specific Clinical Resource Details
-- ============================================================================
-- Example: Get all Conditions for an encounter with details
-- ============================================================================

SELECT 
  id,
  ehr_resource_id,
  data->>'codeText' as condition_name,
  data->>'categoryText' as category,
  data->>'clinicalStatus' as clinical_status,
  data->>'verificationStatus' as verification_status,
  data->>'recordedDate' as recorded_date,
  data->>'encounterReference' as encounter_reference,
  last_synced_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND resource_type::text = 'Condition'
  AND data->>'encounterReference' = 'Encounter/97953483'
ORDER BY data->>'recordedDate' DESC;

-- Expected: 171 conditions


-- ============================================================================
-- Query 8: Get Observations with Values
-- ============================================================================
-- Example: Get all Observations with their values for an encounter
-- ============================================================================

SELECT 
  id,
  ehr_resource_id,
  data->>'codeText' as observation_name,
  data->'valueQuantity'->>'value' as value,
  data->'valueQuantity'->>'unit' as unit,
  data->>'effectiveDateTime' as effective_date,
  data->>'status' as status,
  data->>'encounterReference' as encounter_reference,
  last_synced_at
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND resource_type::text = 'Observation'
  AND data->>'encounterReference' = 'Encounter/97953483'
ORDER BY data->>'effectiveDateTime' DESC;

-- Expected: 67 observations


-- ============================================================================
-- Query 9: Check encounterReference Format
-- ============================================================================
-- Verify the format of encounterReference in the JSONB data column
-- ============================================================================

SELECT 
  resource_type::text,
  data->>'encounterReference' as encounter_ref,
  COUNT(*) as count
FROM fhir_resources
WHERE data->>'encounterReference' IS NOT NULL
GROUP BY resource_type::text, data->>'encounterReference'
ORDER BY count DESC
LIMIT 20;

-- All encounterReference values follow the format: "Encounter/{id}"


-- ============================================================================
-- Query 10: Validate Data Integrity
-- ============================================================================
-- Check for orphaned clinical resources (reference encounters that don't exist)
-- ============================================================================

WITH referenced_encounters AS (
  SELECT DISTINCT 
    REPLACE(data->>'encounterReference', 'Encounter/', '') as encounter_id,
    user_id
  FROM fhir_resources
  WHERE data->>'encounterReference' IS NOT NULL
),
actual_encounters AS (
  SELECT DISTINCT
    ehr_resource_id as encounter_id,
    user_id
  FROM fhir_resources
  WHERE resource_type::text = 'Encounter'
)
SELECT 
  re.encounter_id,
  re.user_id,
  'Missing Encounter' as status
FROM referenced_encounters re
LEFT JOIN actual_encounters ae 
  ON re.encounter_id = ae.encounter_id 
  AND re.user_id = ae.user_id
WHERE ae.encounter_id IS NULL
LIMIT 10;

-- This helps identify data integrity issues


-- ============================================================================
-- Query 11: Performance Check - Index Usage
-- ============================================================================
-- Check if queries are using indexes efficiently
-- ============================================================================

EXPLAIN ANALYZE
SELECT 
  id,
  resource_type::text,
  ehr_resource_id
FROM fhir_resources
WHERE user_id = 'abd7741f-35f1-4cc1-8d57-471921171c04'
  AND (
    (resource_type::text = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    (data->>'encounterReference' = 'Encounter/97953483')
  );

-- Look for:
-- - Index usage on user_id
-- - Index usage on resource_type
-- - Consider adding GIN index on data jsonb column for encounterReference


-- ============================================================================
-- Recommended Indexes for Performance
-- ============================================================================

-- Already exists: CREATE INDEX idx_fhir_resources_user_id ON fhir_resources(user_id);
-- Already exists: CREATE INDEX idx_fhir_resources_user_id_resource_type ON fhir_resources(user_id, resource_type);

-- Recommended: Add GIN index for JSONB queries
-- CREATE INDEX idx_fhir_resources_data_encounter_ref 
-- ON fhir_resources USING GIN ((data -> 'encounterReference'));

-- Or for exact match queries:
-- CREATE INDEX idx_fhir_resources_encounter_reference 
-- ON fhir_resources ((data->>'encounterReference'));


-- ============================================================================
-- Notes
-- ============================================================================
-- 1. Always normalize encounter IDs by removing "Encounter/" prefix
-- 2. The encounterReference field format is: "Encounter/{id}"
-- 3. Resource types are stored as PostgreSQL enum but cast to text for queries
-- 4. All timestamps are in UTC
-- 5. The data column is JSONB, allowing efficient JSON operations
-- 6. Consider adding indexes on frequently queried JSONB fields
-- ============================================================================
