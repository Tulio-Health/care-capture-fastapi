# Common Debug Queries

All queries assume session state is sourced: `source .claude/debug-scratch/session-state.env`

Use `$PROD_HOST`, `$PROD_DB`, `$PROD_PASS`, `$DEV_HOST`, `$DEV_DB`, `$DEV_PASS`, `$USER_ID` variables.

## User Lookup (Node API DB)

```sql
-- By email
SELECT id, user_id, first_name, last_name, email, preferred_language, is_active
FROM user_profiles WHERE email = '<EMAIL>';

-- By name
SELECT id, user_id, first_name, last_name, email, preferred_language, is_active
FROM user_profiles WHERE lower(first_name || ' ' || last_name) LIKE lower('%<NAME>%');
```

## Appointment Details (Node API DB)

```sql
-- All appointments for a user with provider info
SELECT a.id, a.appointment_date, a.status, a.source, a.ehr_entity_id,
       a.purpose, a.appointment_type, a.provider_id,
       rcp.provider_first_name, rcp.provider_last_name, rcp.pri_spec, rcp.npi
FROM appointments a
LEFT JOIN ref_cms_provider_data_loc rcp ON a.provider_id = rcp.id
WHERE a.user_id = '<USER_ID>'
ORDER BY a.appointment_date DESC LIMIT 20;

-- Appointments missing provider
SELECT id, appointment_date, status, source, ehr_entity_id, purpose
FROM appointments
WHERE user_id = '<USER_ID>' AND provider_id IS NULL
ORDER BY appointment_date DESC;
```

## Summary Analysis (Node API DB)

```sql
-- Summary stats: empty vs has content
SELECT CASE WHEN summary_text LIKE 'No document attachments%' THEN 'empty'
            ELSE 'has_content' END AS status,
       metadata->>'source' AS source, count(*)
FROM conversation_summaries WHERE user_id = '<USER_ID>'
GROUP BY 1, 2 ORDER BY 1;

-- All summaries with preview
SELECT cs.id, cs.appointment_id, left(cs.summary_text, 100) AS preview,
       cs.metadata->>'source' AS source, cs.created_at
FROM conversation_summaries cs
WHERE cs.user_id = '<USER_ID>'
ORDER BY cs.created_at DESC;

-- Empty summaries: which encounter types?
SELECT a.purpose, fr.data->>'encounterTypeText' AS encounter_type,
       fr.data->>'classCode' AS class_code, count(*)
FROM conversation_summaries cs
JOIN appointments a ON cs.appointment_id = a.id
LEFT JOIN fhir_resources fr ON a.ehr_entity_id = fr.ehr_resource_id
    AND fr.resource_type = 'Encounter' AND fr.user_id = '<USER_ID>'
WHERE cs.user_id = '<USER_ID>'
  AND cs.summary_text LIKE 'No document attachments%'
GROUP BY 1, 2, 3 ORDER BY count DESC;
```

## FHIR Resources (Node API DB)

```sql
-- Resource counts by type
SELECT resource_type, count(*), max(last_synced_at) AS last_sync
FROM fhir_resources WHERE user_id = '<USER_ID>'
GROUP BY resource_type ORDER BY count DESC;

-- Encounters with provider info
SELECT id, ehr_resource_id, data->>'providerFullName' AS provider,
       data->>'encounterTypeText' AS type, data->>'status' AS status,
       data->>'classCode' AS class_code, data->>'classDisplay' AS class_display,
       data->>'periodStart' AS period_start, data->>'periodEnd' AS period_end
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'Encounter'
ORDER BY data->>'periodStart' DESC NULLS LAST;

-- Encounters for a specific provider
SELECT id, ehr_resource_id, data->>'providerFullName' AS provider,
       data->>'encounterTypeText' AS type, data->>'periodStart' AS period_start,
       data->>'classCode' AS class_code, data->>'providerNpi' AS npi
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'Encounter'
  AND data->>'providerFullName' ILIKE '%<PROVIDER_NAME>%';
```

## DocumentReference Analysis (Node API DB)

```sql
-- DocumentReference field inventory
SELECT jsonb_object_keys(data) AS field, count(*)
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'DocumentReference'
GROUP BY 1 ORDER BY count DESC;

-- DocumentReferences: encounter reference distribution
SELECT count(*) AS total,
       count(data->>'encounterReference') AS has_encounter_ref,
       count(*) - count(data->>'encounterReference') AS orphans
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'DocumentReference';

-- Orphan DocumentReferences (no encounterReference)
SELECT id, data->>'type' AS doc_type,
       data->>'periodStart' AS period_start, data->>'periodEnd' AS period_end
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'DocumentReference'
  AND data->>'encounterReference' IS NULL
ORDER BY data->>'periodStart' DESC NULLS LAST;

-- Check if an encounter has DocumentReferences (by encounter ref AND by date)
SELECT a.appointment_date, a.purpose, a.ehr_entity_id,
    (SELECT count(*) FROM fhir_resources dr
     WHERE dr.user_id = '<USER_ID>' AND dr.resource_type = 'DocumentReference'
       AND dr.data->>'encounterReference' = 'Encounter/' || a.ehr_entity_id
    ) AS docrefs_by_enc_ref,
    (SELECT count(*) FROM fhir_resources dr
     WHERE dr.user_id = '<USER_ID>' AND dr.resource_type = 'DocumentReference'
       AND DATE(dr.data->>'periodStart') = a.appointment_date
    ) AS docrefs_by_date
FROM appointments a
WHERE a.user_id = '<USER_ID>' AND a.source LIKE 'emr_%'
ORDER BY a.appointment_date DESC;
```

## Chatbot Analysis (Node API DB)

```sql
-- Recent chatbot messages
SELECT id, conversation_id, left(user_query, 80) AS query_preview,
       detected_intent, left(ai_response::text, 200) AS response_preview,
       "feedbackType", created_at
FROM chatbot_messages
WHERE conversation_id IN (
    SELECT id FROM chatbot_conversations WHERE user_id = '<USER_ID>'
)
ORDER BY created_at DESC LIMIT 15;

-- Note: feedbackType is camelCase in DB — must quote: "feedbackType"

-- Messages with negative feedback
SELECT id, left(user_query, 80) AS query, detected_intent, "feedbackType", created_at
FROM chatbot_messages
WHERE conversation_id IN (
    SELECT id FROM chatbot_conversations WHERE user_id = '<USER_ID>'
) AND "feedbackType" IN ('dislike', 'flag')
ORDER BY created_at DESC;
```

## EHR Connection Status (EMR Connector DB)

```sql
-- All connections for a user
SELECT c.id, c.user_id, c.is_active, c.sync_enabled,
       c.sync_status, c.last_sync_at, c.sync_metadata,
       p.provider_name, p.fhir_base_url
FROM fhir_ehr_connections c
JOIN fhir_ehr_providers p ON c.provider_id = p.id
WHERE c.user_id = '<USER_ID>';

-- Connections with sync errors
SELECT id, user_id, sync_status, sync_metadata, last_sync_at
FROM fhir_ehr_connections WHERE sync_status = 'error'
ORDER BY last_sync_at DESC LIMIT 20;
```

## Cross-DB Trace: Appointment → FHIR → Summary → DocumentReferences

```sql
-- Full trace for a single appointment
-- Step 1: Appointment details
SELECT id, appointment_date, source, ehr_entity_id, provider_id, purpose, status
FROM appointments WHERE id = '<APPOINTMENT_ID>';

-- Step 2: Linked Encounter
SELECT id, data->>'providerFullName' AS provider, data->>'encounterTypeText' AS type,
       data->>'classCode' AS class, data->>'periodStart' AS period_start
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'Encounter'
  AND ehr_resource_id = '<EHR_ENTITY_ID>';

-- Step 3: Summary
SELECT id, left(summary_text, 100), metadata->>'source', created_at
FROM conversation_summaries WHERE appointment_id = '<APPOINTMENT_ID>';

-- Step 4: DocumentReferences for this encounter
SELECT id, data->>'type', data->>'periodStart', data->>'encounterReference'
FROM fhir_resources
WHERE user_id = '<USER_ID>' AND resource_type = 'DocumentReference'
  AND data->>'encounterReference' = 'Encounter/<EHR_ENTITY_ID>';
```
