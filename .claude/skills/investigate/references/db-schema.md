# Database Schema Reference

> **Canonical source**: Agent memory files `db-schema-nodeapi.md` and `db-schema-emr.md` have verified column names. This file is a quick reference; agent memory is the authority.

## Node API DB (`care-capture-app-dev` / prod name from SSM)

### `appointments`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| userId | user_id | varchar(255) | |
| providerId | provider_id | uuid | FK → `healthcare_providers.id` (nullable) |
| appointmentDate | appointment_date | date | Date only, no timezone. Transformer uses `YYYY-MM-DD`. |
| appointmentTime | appointment_time | time | Nullable |
| timezone | timezone | varchar(50) | Default `America/New_York` |
| appointmentDatetimeUtc | appointment_datetime_utc | timestamptz | Computed, read-only |
| durationMinutes | duration_minutes | integer | Default 30 |
| purpose | purpose | text | Encounter type text from FHIR (e.g. `Follow Up`, `Telephone MPM`) |
| location | location | text | |
| status | status | enum | `proposed`, `pending`, `scheduled`, `booked`, `arrived`, `fulfilled`, `cancelled`, `noshow`, `entered_in_error`, `checked_in`, `waitlist` |
| quickRecordingStatus | quick_recording_status | enum | `started`, `provider_pending`, `provider_updated` (nullable) |
| reminderSent | reminder_sent | boolean | Default false |
| appointmentType | appointment_type | enum | `amb`, `emer`, `imp`, `prenc`, `vr`, `hh`, `ss`, `hospitalization` |
| source | source | enum | `emr_epic`, `emr_cerner`, `emr_meditech`, `emr_allscripts`, `emr_athenahealth`, `care_capture_visit`, `care_capture_quick_recording` |
| ehrEntityId | ehr_entity_id | varchar(255) | FHIR encounter/appointment resource ID from EHR (nullable) |
| hospitalizationEndDate | hospitalization_end_date | date | Nullable |
| createdBy/createdAt/updatedBy/updatedAt | audit columns | | |

### `conversation_summaries`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| appointmentId | appointment_id | uuid | FK → appointments.id |
| userId | user_id | varchar | |
| summaryText | summary_text | text | Empty summaries say `"No document attachments found for this appointment."` |
| metadata | metadata | jsonb | `source`: `'transcript'` \| `'attachment_summary'` \| `'fhir_analysis'` |
| createdAt/updatedAt | | timestamptz | |

### `conversation_summary_translations`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| summaryId | summary_id | uuid | FK → conversation_summaries.id |
| languageCode | language_code | varchar | e.g. `es`, `fr`, `ar` |
| isActive | is_active | boolean | |
| translatedAt | translated_at | timestamptz | |
| translatedText | translated_text | text | |

### `user_profiles`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| userId | user_id | varchar | Clerk user ID (unique) |
| firstName/lastName/email | | varchar | |
| preferredLanguage | preferred_language | varchar | BCP-47 code |
| isActive | is_active | boolean | |

### `fhir_resources`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| userId | user_id | varchar | |
| resourceType | resource_type | varchar | `Encounter`, `DocumentReference`, `Patient`, `Observation`, `Condition`, `Procedure`, `MedicationRequest`, `DiagnosticReport` |
| ehrResourceId | ehr_resource_id | varchar | FHIR resource ID from EHR |
| ehrConnectionId | ehr_connection_id | uuid | |
| ehrProvider | ehr_provider | varchar | `epic`, `cerner`, etc. |
| data | data | jsonb | Full mapped FHIR data (see JSONB fields below) |
| jobId | job_id | uuid | Sync job that created/updated this |
| lastSyncedAt | last_synced_at | timestamptz | |

#### `fhir_resources.data` JSONB fields by resource_type

**Encounter**:
- `classCode` — e.g. `Ambulatory`, `Support OP Encounter`
- `classDisplay` — may be empty for some EHR vendors
- `periodStart`, `periodEnd` — ISO datetime strings
- `status` — `unknown`, `planned`, `finished`, etc.
- `encounterTypeText` — e.g. `Follow Up`, `Telephone MPM`, `Outpatient Surgery`
- `providerNpi`, `providerFullName`, `providerFirstName`, `providerLastName`
- `serviceProviderNpi`, `serviceProviderName`
- `locationName`, `reasonText`

**DocumentReference**:
- `encounterReference` — `Encounter/<ehr_resource_id>` format (71/84 have this for tested user; 13 orphans don't)
- `type` — e.g. `CCD Document`, `Encounter Summary`, `Op Note`, `Progress Notes`
- `periodStart`, `periodEnd` — date or datetime strings
- `status` — `current`, etc.
- `attachments` — JSONB array of attachment objects
- `contentUrl` — URL to fetch document content
- `categoryText`, `categoryCodes`, `contentType`, `contentFormat`

### Provider tables
| Table | Notes |
|---|---|
| `ref_cms_provider_data_loc` | **Main provider table**. FK from `appointments.provider_id`. Entity: `CmsProviderEntity`. Columns: `npi`, `provider_first_name`, `provider_last_name`, `provider_middle_name`, `pri_spec`, `facility_name`, `credentials`, `suffix`, `gndr`, `latitude`, `longitude`, `location`, `search_vector`, etc. Used by both Node API and FastAPI. |
| `healthcare_providers` | **DEPRECATED — scheduled for drop.** Legacy table, only referenced in seed-data. Not used in business logic. |
| `provider_favorites` | User provider favorites |

### Chatbot tables

**`chatbot_conversations`**:
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| userId | user_id | uuid | |
| context | context | enum | `general_question`, `appointment_scheduling`, `medication_reminder`, `health_insight` |
| startTimestamp | start_timestamp | timestamp | |
| endTimestamp | end_timestamp | timestamp | nullable |

**`chatbot_messages`**:
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| conversationId | conversation_id | uuid | FK → chatbot_conversations.id |
| userQuery | user_query | text | |
| aiResponses | ai_response | jsonb | Array of `{type, content, data}` |
| detectedIntent | detected_intent | enum | `past_visits`, `health_insights`, `upcoming_visits`, `manage_visits`, `end_conversation`, `medical_inquiry`, `unknown`, `not_a_valid_option` |
| feedbackType | "feedbackType" | enum | `like`, `dislike`, `flag` (nullable). **Note**: camelCase column name — must quote in SQL: `"feedbackType"` |

---

## EMR Connector DB (`care-capture-emr-dev` / `care-capture-emr-prod`)

### `fhir_ehr_connections`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| userId | user_id | varchar | Clerk user ID (e.g. `user_xxx`) |
| providerId | provider_id | uuid | FK → fhir_ehr_providers.id |
| vendorId | vendor_id | uuid | FK → vendors.id |
| isActive | is_active | boolean | |
| syncEnabled | sync_enabled | boolean | |
| lastSyncAt | last_sync_at | timestamptz | |
| syncStatus | sync_status | varchar | `idle`, `syncing`, `error`, `paused` |
| syncMetadata | sync_metadata | jsonb | Error details, job state |

### `fhir_resource_cache`
| Column | DB Column Name | Type | Notes |
|--------|---------------|------|-------|
| id | id | uuid | PK |
| connectionId | connection_id | uuid | FK → fhir_ehr_connections.id |
| resourceType | resource_type | varchar | `Encounter`, `Patient`, etc. |
| resourceId | resource_id | varchar | FHIR resource ID |
| rawData | raw_data | jsonb | Raw FHIR from EHR |
| mappedData | mapped_data | jsonb | Normalized version |
| jobId | job_id | uuid | |

### `fhir_ehr_providers`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| provider_name | varchar | e.g. `Epic`, `Cerner` |
| fhir_base_url | varchar | |
| client_id | varchar | OAuth client ID |
| fhir_version | varchar | `R4`, `DSTU2` |
| is_active / is_sandbox | boolean | |

### Audit tables
- `fhir_ehr_connections_history` — populated by triggers
- `fhir_resource_cache_history` — populated by triggers
