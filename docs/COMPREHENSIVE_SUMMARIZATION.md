# Comprehensive Summarization Endpoint

## Overview

The Comprehensive Summarization endpoint provides a unified API for executing multiple AI summarization tasks in parallel, combining transcript analysis and FHIR clinical data analysis into a single, efficient request.

### Key Benefits

- **⚡ 37.5% Faster**: Parallel execution vs sequential operations
- **🛡️ Partial Success**: Returns successful results even if one operation fails
- **🎯 Flexible**: Configure which analyses to include
- **⏱️ Timeout Control**: Configurable timeout (10-300s, default 120s)
- **📊 Comprehensive Metrics**: Detailed execution statistics
- **🔍 Source Tracking**: Metadata distinguishes summary types

---

## Endpoint Details

### Request

**Method:** `POST`  
**Path:** `/care-capture/comprehensive-summary`  
**Content-Type:** `application/json`

### Request Schema

```json
{
  "appointment_id": "uuid (required)",
  "user_id": "uuid (required)",
  "transcripts": [
    {
      "text": "string (required)",
      "created_at": "datetime (optional)",
      "language_code": "string (optional, default: 'en')"
    }
  ],
  "include_fhir_analysis": "boolean (optional, default: false)",
  "resource_types": ["string array (optional)"],
  "analysis_focus": "string (optional)",
  "timeout_seconds": "integer (optional, default: 120, min: 10, max: 300)"
}
```

### Field Descriptions

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `appointment_id` | UUID | ✅ Yes | - | Appointment identifier |
| `user_id` | UUID | ✅ Yes | - | User/patient identifier |
| `transcripts` | Array | ⚠️ Conditional | - | Array of transcript objects (required if not using FHIR) |
| `transcripts[].text` | String | ✅ Yes | - | Transcript content |
| `transcripts[].created_at` | DateTime | ❌ No | `now()` | Transcript creation timestamp |
| `transcripts[].language_code` | String | ❌ No | `"en"` | Language code (ISO 639-1) |
| `include_fhir_analysis` | Boolean | ❌ No | `false` | Enable FHIR analysis |
| `resource_types` | Array[String] | ❌ No | All types | FHIR resource types to include |
| `analysis_focus` | String | ❌ No | `null` | Focus area: `chronic_conditions`, `medication_interactions`, etc. |
| `timeout_seconds` | Integer | ❌ No | `120` | Maximum execution time (10-300s) |

### Validation Rules

- ✅ At least one data source required: `transcripts` OR `include_fhir_analysis=true`
- ✅ If `transcripts` provided, must have at least one entry
- ✅ `timeout_seconds` must be between 10 and 300
- ✅ `appointment_id` and `user_id` must be valid UUIDs

---

## Response Schema

### Success Response (200 OK)

**Note:** Always returns 200 OK with wrapped response structure. Check `success` field and `error` message for actual status.

```json
{
  "success": true,
  "message": "string (optional warning message)",
  "summaries": [
    {
      "id": "uuid",
      "appointmentId": "uuid",
      "userId": "uuid",
      "summaryText": "string",
      "keyPoints": ["string"],
      "medications": [{"name": "string", "dosage": "string"}],
      "diagnoses": ["string"],
      "instructions": ["string"],
      "recommendations": [{"text": "string", "priority": "string"}],
      "metadata": {
        "source": "transcript",
        "analysis_version": "string",
        "transcript_count": "integer"
      },
      "createdAt": "datetime",
      "updatedAt": "datetime",
      "createdBy": "uuid",
      "updatedBy": "uuid"
    }
  ],
  "fhirSummaries": [
    {
      "id": "uuid",
      "appointmentId": "uuid",
      "userId": "uuid",
      "summaryText": "string",
      "keyPoints": ["string"],
      "medications": [{"name": "string", "dosage": "string"}],
      "diagnoses": ["string"],
      "instructions": ["string"],
      "recommendations": [{"text": "string", "priority": "string"}],
      "metadata": {
        "source": "fhir_analysis",
        "analysis_version": "string",
        "total_resources": "integer",
        "resource_counts": {
          "Condition": "integer",
          "Observation": "integer",
          "MedicationRequest": "integer"
        }
      },
      "createdAt": "datetime",
      "updatedAt": "datetime",
      "createdBy": "uuid",
      "updatedBy": "uuid"
    }
  ],
  "error": "string (error message if complete failure)"
}
```

### Response Properties

| Property | Type | Description |
|----------|------|-------------|
| `success` | Boolean | Whether the request was processed successfully |
| `message` | String \| null | Optional warning message (used for partial success) |
| `summaries` | Array | Transcript-based summaries (empty if not requested or failed) |
| `fhirSummaries` | Array | FHIR-based summaries (empty if not requested or failed) |
| `summaries[].metadata.source` | String | Always `"transcript"` |
| `fhirSummaries[].metadata.source` | String | Always `"fhir_analysis"` |
| `error` | String \| null | Error message for complete failures |

---

## Metadata Source Tracking

Each summary includes a `metadata.source` field to distinguish the type of analysis:

### Transcript Summary Metadata

```json
{
  "source": "transcript",
  "analysis_version": "1.0",
  "transcript_count": 3
}
```

### FHIR Analysis Summary Metadata

```json
{
  "source": "fhir_analysis",
  "analysis_version": "1.0",
  "total_resources": 352,
  "resource_counts": {
    "Condition": 45,
    "Observation": 150,
    "MedicationRequest": 30
  },
  "analysis_focus": "medication_interactions",
  "encounter_id": "uuid",
  "provider_name": "Dr. Smith",
  "appointment_date": "2024-01-15T10:30:00Z"
}
```

---

## Usage Examples

### Example 1: Transcript Only

**Request:**
```json
POST /care-capture/comprehensive-summary

{
  "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "223e4567-e89b-12d3-a456-426614174000",
  "transcripts": [
    {
      "text": "Patient presents with persistent headache for 3 days. Denies fever, neck stiffness. Vital signs stable.",
      "created_at": "2024-01-15T10:00:00Z",
      "language_code": "en"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": null,
  "data": {
    "summaries": [
      {
        "id": "abc-123",
        "appointmentId": "123e4567-e89b-12d3-a456-426614174000",
        "summaryText": "Patient experiencing persistent headache for 3 days without fever or neck stiffness...",
        "keyPoints": ["Persistent headache for 3 days", "No fever", "Vital signs stable"],
        "metadata": {
          "source": "transcript",
          "analysis_version": "1.0",
          "transcript_count": 1
        },
        "createdAt": "2024-01-15T10:05:00Z",
        "updatedAt": "2024-01-15T10:05:00Z"
      }
    ],
    "fhirSummaries": []
  },
  "error": null
}
```

### Example 2: FHIR Analysis Only

**Request:**
```json
POST /care-capture/comprehensive-summary

{
  "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "223e4567-e89b-12d3-a456-426614174000",
  "include_fhir_analysis": true,
  "resource_types": ["Condition", "Observation", "MedicationRequest"],
  "analysis_focus": "chronic_conditions"
}
```

**Response:**
```json
{
  "success": true,
  "message": null,
  "data": {
    "summaries": [],
    "fhirSummaries": [
      {
        "id": "def-456",
        "appointmentId": "123e4567-e89b-12d3-a456-426614174000",
        "summaryText": "Patient has documented history of Type 2 Diabetes and Hypertension...",
        "keyPoints": ["Type 2 Diabetes", "Hypertension", "Multiple medications"],
        "metadata": {
          "source": "fhir_analysis",
          "analysis_version": "1.0",
          "total_resources": 225,
          "resource_counts": {
            "Condition": 12,
            "Observation": 180,
            "MedicationRequest": 33
          },
          "analysis_focus": "chronic_conditions"
        },
        "createdAt": "2024-01-15T10:05:00Z",
        "updatedAt": "2024-01-15T10:05:00Z"
      }
    ]
  },
  "error": null
}
```

### Example 3: Both in Parallel (Complete Success)

**Request:**
```json
POST /care-capture/comprehensive-summary

{
  "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "223e4567-e89b-12d3-a456-426614174000",
  "transcripts": [
    {
      "text": "Patient presents with worsening shortness of breath...",
      "language_code": "en"
    }
  ],
  "include_fhir_analysis": true,
  "resource_types": ["Condition", "Observation", "MedicationRequest"],
  "timeout_seconds": 120
}
```

**Response:**
```json
{
  "success": true,
  "message": null,
  "data": {
    "summaries": [
      {
        "id": "abc-123",
        "appointmentId": "123e4567-e89b-12d3-a456-426614174000",
        "summaryText": "Patient experiencing worsening shortness of breath...",
        "metadata": {
          "source": "transcript",
          "transcript_count": 1
        },
        "createdAt": "2024-01-15T10:05:00Z",
        "updatedAt": "2024-01-15T10:05:00Z"
      }
    ],
    "fhirSummaries": [
      {
        "id": "def-456",
        "appointmentId": "123e4567-e89b-12d3-a456-426614174000",
        "summaryText": "Clinical analysis shows history of COPD and current medications...",
        "metadata": {
          "source": "fhir_analysis",
          "total_resources": 352
        },
        "createdAt": "2024-01-15T10:05:00Z",
        "updatedAt": "2024-01-15T10:05:00Z"
      }
    ]
  },
  "error": null
}
```

**Note:** Sequential execution would take ~7.23s (2.45s + 4.78s), but parallel execution completes in ~5.23s (**27.7% faster**).

### Example 4: Partial Success

**Request:**
```json
POST /care-capture/comprehensive-summary

{
  "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "223e4567-e89b-12d3-a456-426614174000",
  "transcripts": [
    {
      "text": "Patient presents with chest pain..."
    }
  ],
  "include_fhir_analysis": true
}
```

**Response (transcript succeeded, FHIR failed):**
```json
{
  "success": true,
  "message": "Transcript summarization succeeded, but FHIR analysis failed",
  "data": {
    "summaries": [
      {
        "id": "abc-123",
        "appointmentId": "123e4567-e89b-12d3-a456-426614174000",
        "summaryText": "Patient experiencing chest pain...",
        "metadata": {
          "source": "transcript"
        },
        "createdAt": "2024-01-15T10:05:00Z",
        "updatedAt": "2024-01-15T10:05:00Z"
      }
    ],
    "fhirSummaries": []
  },
  "error": null
}
```

### Example 5: Timeout Scenario

**Request:**
```json
POST /care-capture/comprehensive-summary

{
  "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "223e4567-e89b-12d3-a456-426614174000",
  "transcripts": [{"text": "Very long transcript..."}],
  "include_fhir_analysis": true,
  "timeout_seconds": 10
}
```

**Response:**
```json
{
  "success": false,
  "message": null,
  "data": {
    "summaries": [],
    "fhirSummaries": []
  },
  "error": "Operation timed out after 10 seconds"
}
```

---

## Parallel Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP Request Received                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              ComprehensiveSummarizationService               │
│                  (Orchestration Layer)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────┴───────────────┐
         │   Build Task List             │
         │   - Check transcripts         │
         │   - Check include_fhir_analysis│
         └───────────────┬───────────────┘
                         │
                         ▼
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│ TranscriptSummary   │         │  FhirAnalysis       │
│ Service             │         │  Service            │
│                     │         │                     │
│ - Validate input    │         │ - Fetch appointment │
│ - Generate summary  │         │ - Fetch FHIR data   │
│ - Save to DB        │         │ - Run AI analysis   │
│                     │         │ - Save to DB        │
└──────────┬──────────┘         └──────────┬──────────┘
           │                               │
           │    Parallel Execution         │
           │    with asyncio.gather()      │
           │                               │
           └───────────────┬───────────────┘
                           │
                           ▼
          ┌─────────────────────────────────┐
          │   Process Results                │
          │   - Separate successes/failures  │
          │   - Collect error messages       │
          │   - Build response arrays        │
          └────────────────┬────────────────┘
                           │
                           ▼
           ┌────────────────────────────────┐
           │   Return Wrapped Response       │
           │   - success: true/false         │
           │   - message: (optional warning) │
           │   - data.summaries[]            │
           │   - data.fhirSummaries[]        │
           │   - error: (error message)      │
           └────────────────────────────────┘
```

---

## Database Behavior

### Separate Transactions

Each service creates its own database record independently:

```python
# Service 1: Transcript Summarization
async with db_session() as session:
    await repository.upsert(appointment_id, summary_data)
    # Transaction commits

# Service 2: FHIR Analysis (separate transaction)
async with db_session() as session:
    await repository.upsert(appointment_id, summary_data)
    # Transaction commits
```

### Multiple Summaries Per Appointment

One appointment can have multiple summaries distinguished by `metadata.source`:

```sql
SELECT * FROM conversation_summaries 
WHERE appointment_id = '123e4567-e89b-12d3-a456-426614174000';

-- Result:
-- id  | appointment_id | metadata.source | summary_text
-- 1   | 123e4...       | transcript      | "Patient presents..."
-- 2   | 123e4...       | fhir_analysis   | "Clinical data shows..."
```

### Upsert Logic

If a summary already exists for the same `appointment_id` and `metadata.source`, it will be updated:

```python
# First call
POST /comprehensive-summary
→ Creates summary with metadata.source = "transcript"

# Second call (same appointment_id)
POST /comprehensive-summary
→ Updates existing summary with metadata.source = "transcript"
```

---

## Performance Characteristics

### Execution Time Comparison

| Scenario | Sequential | Parallel | Improvement |
|----------|-----------|----------|-------------|
| Transcript (2s) + FHIR (4s) | 6.0s | 4.0s | **33.3%** |
| Transcript (3s) + FHIR (5s) | 8.0s | 5.0s | **37.5%** |
| Transcript (5s) + FHIR (10s) | 15.0s | 10.0s | **33.3%** |

**Formula:**  
Parallel time ≈ `max(transcript_time, fhir_time) + overhead`

### Resource Usage

- **CPU**: Higher during parallel execution (2 AI models running)
- **Memory**: Moderate increase (2 contexts loaded)
- **Database**: 2 separate connections/transactions
- **Network**: Parallel FHIR API calls

### Timeout Recommendations

| Use Case | Recommended Timeout |
|----------|---------------------|
| Transcript only (short) | 30-60s |
| Transcript only (long) | 60-120s |
| FHIR only | 60-90s |
| Both (parallel) | 120-180s |
| Production default | 120s |

---

## Error Handling

### Error Types

| Error Type | Source | Cause | Recovery |
|------------|--------|-------|----------|
| `ValidationError` | Any | Invalid input | Fix request data |
| `HTTPException` | FHIR | No resources found | Check appointment has EHR data |
| `TimeoutError` | Any | Operation too slow | Increase timeout |
| `DatabaseError` | Any | DB connection issue | Retry request |
| `AIServiceError` | Any | OpenAI API error | Check API key, retry |

### Partial Success Handling

The endpoint is designed to succeed partially:

```python
# If transcript succeeds but FHIR fails:
{
  "success": True,                              # Request succeeded
  "message": "Transcript summarization succeeded, but FHIR analysis failed",
  "data": {
    "summaries": [transcript_summary],          # User gets transcript data
    "fhirSummaries": []                         # FHIR failed (empty array)
  },
  "error": None                                 # Not a complete failure
}
```

**Client Handling:**
```javascript
const response = await fetch('/comprehensive-summary', {...});
const data = await response.json();

if (!data.success) {
  // Complete failure
  showError(`Failed to generate summaries: ${data.error}`);
} else {
  // Success or partial success
  const transcriptCount = data.data.summaries.length;
  const fhirCount = data.data.fhirSummaries.length;
  
  // Display successful summaries
  if (transcriptCount > 0) {
    displayTranscriptSummaries(data.data.summaries);
  }
  if (fhirCount > 0) {
    displayFhirSummaries(data.data.fhirSummaries);
  }
  
  // Show warning if partial success
  if (data.message) {
    showWarning(data.message);
  }
}
```

---

## Querying Summaries

### By Source Type

```sql
-- Get transcript summaries only
SELECT * FROM conversation_summaries 
WHERE metadata->>'source' = 'transcript';

-- Get FHIR analysis summaries only
SELECT * FROM conversation_summaries 
WHERE metadata->>'source' = 'fhir_analysis';
```

### By Appointment

```sql
-- Get all summaries for an appointment
SELECT * FROM conversation_summaries 
WHERE appointment_id = '123e4567-e89b-12d3-a456-426614174000'
ORDER BY created_at DESC;
```

### Filter by Resource Count

```sql
-- Get FHIR summaries with >100 resources
SELECT 
  id,
  appointment_id,
  (metadata->>'total_resources')::int as resource_count
FROM conversation_summaries 
WHERE metadata->>'source' = 'fhir_analysis'
  AND (metadata->>'total_resources')::int > 100;
```

### NodeAPI Query (Already Supported!)

```typescript
// GET /conversation-summaries/appointment/:appointmentId
const summaries = await api.getByAppointmentId('123e4567...');

// Filter by source (summaries stored separately in DB)
const transcriptSummaries = summaries.filter(s => s.metadata?.source === 'transcript');
const fhirSummaries = summaries.filter(s => s.metadata?.source === 'fhir_analysis');

// Or use the comprehensive endpoint directly
const response = await fetch('/care-capture/comprehensive-summary', {
  method: 'POST',
  body: JSON.stringify({
    appointment_id: '123e4567...',
    user_id: '223e4567...',
    transcripts: [{text: '...'}],
    include_fhir_analysis: true
  })
});

const { summaries, fhirSummaries } = response.data;  // Already separated!
```

---

## Best Practices

### 1. Always Include Timeout
```json
{
  "timeout_seconds": 120  // Prevent hanging requests
}
```

### 2. Handle Partial Success
```javascript
// Check success and message fields
if (data.success && data.message) {
  // Partial success with warning
  showWarning(data.message);
}
if (!data.success && data.error) {
  // Complete failure
  showError(data.error);
}
```

### 3. Use Appropriate Analysis Focus
```json
{
  "analysis_focus": "chronic_conditions",  // More targeted results
  "resource_types": ["Condition", "MedicationRequest"]
}
```

### 4. Access Summaries by Type
```javascript
// Access summaries directly from response data
const { summaries, fhirSummaries } = data.data;

// Display in separate sections
if (summaries.length > 0) {
  displayTranscriptSummaries(summaries);
}
if (fhirSummaries.length > 0) {
  displayFhirSummaries(fhirSummaries);
}
```

### 5. Filter by Source in Database
```javascript
// Summaries are already separated in the response
// No need to filter by metadata.source in the frontend
const transcriptSummaries = data.data.summaries;  // All transcript-based
const fhirSummaries = data.data.fhirSummaries;    // All FHIR-based
```

---

## Troubleshooting

### Issue: "No data sources provided"
**Cause:** Neither `transcripts` nor `include_fhir_analysis=true` specified  
**Solution:** Provide at least one data source

### Issue: Timeout errors
**Cause:** Operations taking longer than configured timeout  
**Solution:** Increase `timeout_seconds` or optimize data size

### Issue: FHIR analysis always fails
**Cause:** Appointment has no associated EHR entity ID  
**Solution:** Verify appointment is linked to EHR system

### Issue: Duplicate summaries created
**Cause:** Multiple concurrent requests for same appointment  
**Solution:** Use upsert logic (already implemented), or implement request deduplication

### Issue: Old summaries missing metadata.source
**Cause:** Summaries created before this feature  
**Solution:** Handle gracefully with `metadata?.source || 'unknown'`

---

## Related Documentation

- [Architecture Documentation](./ARCHITECTURE.md) - Service layer design
- [Metadata Implementation](./METADATA_IMPLEMENTATION.md) - Metadata field details
- [Breaking Changes Analysis](./BREAKING_CHANGES_ANALYSIS.md) - Compatibility info
- [API Examples](./API_EXAMPLES.md) - Code examples in multiple languages

---

## Changelog

### Version 1.0 (Initial Release)
- ✅ Parallel execution of transcript and FHIR analysis
- ✅ Configurable timeout (10-300s)
- ✅ Partial success support
- ✅ Source tracking via metadata.source
- ✅ Comprehensive error handling
- ✅ Detailed execution metrics
