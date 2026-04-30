# Cross-Service Debugging Workflows

Each workflow is a numbered sequence. Run steps in order and stop when you find the root cause.

---

## 1. Missing Provider on Appointment

**Question**: "Why doesn't appointment X have a provider ID?"

1. **Check appointment** (Node API DB — `care-capture-app-dev`):
   ```sql
   SELECT id, user_id, provider_id, source, ehr_entity_id, appointment_type, status
   FROM appointments WHERE id = '<APPOINTMENT_ID>';
   ```

2. **If `source::text = 'manual'`**: Provider was not entered by user — no further action needed. Inform user.

3. **If `source::text LIKE 'emr_%'` or `source::text = 'fhir'`**: Check if the FHIR Encounter has provider data (Node API DB):
   ```sql
   SELECT id, data->>'providerNpi' AS provider_npi, data->>'providerFullName' AS provider_full_name,
          data->>'providerFirstName' AS provider_first_name, data->>'status' AS encounter_status
   FROM fhir_resources
   WHERE user_id = '<USER_ID>' AND resource_type = 'Encounter' AND ehr_resource_id = '<EHR_ENTITY_ID>';
   ```

4. **If FHIR Encounter has no provider data**: Check the raw Encounter cache in EMR DB (`care-capture-emr-dev`).
   Note: EMR connector uses Clerk IDs (`user_xxx`), not UUIDs — look up `connection_id` via a known `ehr_entity_id` instead:
   ```sql
   -- Step 4a: find connection_id from a known ehr_entity_id
   SELECT connection_id FROM fhir_resource_cache
   WHERE resource_id = '<EHR_ENTITY_ID>' LIMIT 1;

   -- Step 4b: fetch the raw Encounter
   SELECT raw_data->'participant' AS participants, mapped_data, job_id
   FROM fhir_resource_cache
   WHERE connection_id = '<CONNECTION_ID>'
     AND resource_type = 'Encounter' AND resource_id = '<EHR_ENTITY_ID>';
   ```

4b. **Check Practitioner NPI in EMR cache** — if the Encounter references a Practitioner, check if that Practitioner resource has an NPI (EMR DB):
   ```sql
   -- Find referenced Practitioner resource_id from the raw Encounter participant array
   SELECT resource_id, raw_data->>'id' AS fhir_id,
          raw_data->'identifier' AS identifiers,
          raw_data->'name' AS names
   FROM fhir_resource_cache
   WHERE connection_id = '<CONNECTION_ID>'
     AND resource_type = 'Practitioner'
     AND resource_id = '<PRACTITIONER_RESOURCE_ID>';
   ```
   If the Practitioner has no NPI in `raw_data->'identifier'`, that is the root cause — the EHR did not provide NPI for this provider.

5. **Check EMR Connector logs** for the sync job that fetched this encounter:
   ```bash
   START=$(date -v-48H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9/application" \
     --start-time $START \
     --filter-pattern '"<EHR_ENTITY_ID>"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

6. **If NPI present in raw data but provider_id is null in appointments**: The NPI-to-provider lookup failed. Check if NPI exists in `ref_cms_provider_data_loc` (Node API DB):
   ```sql
   SELECT id, npi, provider_first_name, provider_last_name, pri_spec
   FROM ref_cms_provider_data_loc WHERE npi = '<NPI>';
   ```

---

## 2. Summary Not Generated

**Question**: "Why wasn't a summary generated for appointment X?"

1. **Check if summary exists** (Node API DB):
   ```sql
   SELECT id, metadata->>'source' AS source, length(summary_text) AS text_len, created_at
   FROM conversation_summaries WHERE appointment_id = '<APPOINTMENT_ID>';
   ```
   If found: summary exists. Check if it's a translation issue instead (see Workflow 4).

2. **Check appointment recording status** (Node API DB):
   ```sql
   SELECT id, status, quick_recording_status, source, appointment_date
   FROM appointments WHERE id = '<APPOINTMENT_ID>';
   ```
   If `quick_recording_status != 'completed'`: recording may not have been processed.

2b. **If appointment is EHR-synced** (`source::text LIKE 'emr_%'`): Check if the summary came from `attachment_summary` source (generated from DocumentReference attachments, not recordings):
   ```sql
   SELECT id, metadata->>'source' AS source, length(summary_text) AS text_len,
          left(summary_text, 100) AS preview, created_at
   FROM conversation_summaries WHERE appointment_id = '<APPOINTMENT_ID>';
   ```
   - If `source = 'attachment_summary'` and preview is `"No document attachments found for this appointment."` (51 chars): check DocumentReference FHIR resources linked to this encounter:
     ```sql
     SELECT id, data->>'status' AS status, data->>'type' AS doc_type,
            data->>'description' AS description, last_synced_at
     FROM fhir_resources
     WHERE user_id = '<USER_ID>' AND resource_type = 'DocumentReference'
       AND data->>'encounter' ILIKE '%<EHR_ENTITY_ID>%';
     ```
     - **No DocRefs found**: Expected for Telephone/Orders Only encounters — EHR did not attach clinical documents.
     - **DocRefs exist but summary is thin**: Sparse clinical content in the EHR document (e.g. brief note or scanned image with no extractable text).
   - Also check `encounterTypeText` in the FHIR Encounter to understand visit classification:
     ```sql
     SELECT data->>'encounterTypeText' AS encounter_type, data->>'classCode' AS class_code,
            data->>'status' AS status
     FROM fhir_resources
     WHERE user_id = '<USER_ID>' AND resource_type = 'Encounter'
       AND ehr_resource_id = '<EHR_ENTITY_ID>';
     ```
     This explains "why is this showing as Telephone when it should be in-person" type questions.

3. **Search Node API logs** for summary generation events:
   ```bash
   START=$(date -v-48H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab/application" \
     --start-time $START \
     --filter-pattern '"<APPOINTMENT_ID>"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

4. **Search FastAPI logs** for AI processing failures:
   ```bash
   START=$(date -v-48H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6/application" \
     --start-time $START \
     --filter-pattern '"<APPOINTMENT_ID>"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

---

## 3. EMR Sync Failures

**Question**: "Why did the sync fail for user X?" or "Why is FHIR data missing?"

1. **Check connection status** (EMR DB):
   ```sql
   SELECT id, sync_status, last_sync_at, sync_metadata, sync_enabled, is_active
   FROM fhir_ehr_connections WHERE user_id = '<USER_ID>';
   ```
   If `sync_status = 'error'`: check `sync_metadata` for error details.

2. **Check what was cached in the last sync** (EMR DB):
   ```sql
   SELECT resource_type, count(*), max(updated_at) AS last_update
   FROM fhir_resource_cache
   WHERE connection_id = '<CONNECTION_ID>'
   GROUP BY resource_type ORDER BY last_update DESC;
   ```

3. **Check EMR Connector logs** for the failing connection:
   ```bash
   START=$(date -v-24H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9/application" \
     --start-time $START \
     --filter-pattern '"<USER_ID>"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

4. **Check if FHIR resources landed in Node API** (Node API DB):
   ```sql
   SELECT resource_type, count(*), max(last_synced_at) AS last_sync
   FROM fhir_resources WHERE user_id = '<USER_ID>'
   GROUP BY resource_type;
   ```
   **Note**: Encounters with `classCode = 'Appointment'` in Epic (MAPS scheduling records, some Office Visits) are filtered out by the pipeline and will not appear as appointments in Node API. This is expected behaviour — only `classCode = 'ambulatory'` (and similar clinical class codes) are imported.

---

## 4. Translation Failures

**Question**: "Why isn't the summary translated for user X?"

1. **Check user's preferred language** (Node API DB):
   ```sql
   SELECT user_id, preferred_language FROM user_profiles WHERE user_id = '<USER_ID>';
   ```

2. **Check translation records** (Node API DB):
   ```sql
   SELECT t.id, t.language_code, t.is_active, t.translated_at,
          t.translated_text IS NOT NULL AS has_text
   FROM conversation_summary_translations t
   JOIN conversation_summaries cs ON t.summary_id = cs.id
   WHERE cs.user_id = '<USER_ID>'
   ORDER BY t.translated_at DESC;
   ```

3. **Search FastAPI logs** for translation requests:
   ```bash
   START=$(date -v-24H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6/application" \
     --start-time $START \
     --filter-pattern '"translate"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

4. **Search Node API logs** for translation dispatch:
   ```bash
   START=$(date -v-24H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab/application" \
     --start-time $START \
     --filter-pattern '?"translation" ?"translate"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```

---

## 5. EHR Connection Issues

**Question**: "Why can't the user connect their EHR?" or "Why is the EHR connection broken?"

1. **Check connection state** (EMR DB):
   ```sql
   SELECT id, is_active, sync_enabled, sync_status, sync_metadata,
          external_connection_id, last_sync_at
   FROM fhir_ehr_connections WHERE user_id = '<USER_ID>';
   ```

2. **Check provider/vendor config** (EMR DB):
   ```sql
   SELECT p.provider_name, p.fhir_base_url, p.client_id, p.fhir_version,
          p.is_active, p.is_sandbox, v.vendor_name AS vendor
   FROM fhir_ehr_connections c
   JOIN fhir_ehr_providers p ON c.provider_id = p.id
   JOIN vendors v ON c.vendor_id = v.id
   WHERE c.user_id = '<USER_ID>';
   ```

3. **Check connection history** for when it broke (EMR DB):
   ```sql
   SELECT sync_status, sync_metadata, last_sync_at, changed_at
   FROM fhir_ehr_connections_history
   WHERE id = '<CONNECTION_ID>'
   ORDER BY changed_at DESC LIMIT 10;
   ```

4. **Search EMR Connector logs** for auth/token errors:
   ```bash
   START=$(date -v-48H -u +%s)000
   aws logs filter-log-events \
     --log-group-name "/aws/apprunner/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9/application" \
     --start-time $START \
     --filter-pattern '?"<USER_ID>" ?"<CONNECTION_ID>"' \
     --profile tuliodev --region us-east-2 \
     --query 'events[*].message' --output text
   ```
