# Metadata Implementation for Conversation Summaries

## Overview
This document describes the metadata implementation for the `conversation_summaries` table, which tracks the source and context of AI-generated summaries from different data sources.

## Database Schema

### Table: `conversation_summaries`

The `metadata` column (JSONB) stores additional information about how the summary was generated:

```sql
metadata JSON NULL
```

### Metadata Structure

#### For Transcript Summaries (source: "transcript")
```json
{
  "source": "transcript",
  "analysis_version": "1.0",
  "transcript_count": 3
}
```

#### For FHIR Analysis Summaries (source: "fhir_analysis")
```json
{
  "source": "fhir_analysis",
  "analysis_version": "1.0",
  "total_resources": 352,
  "resource_counts": {
    "Condition": 45,
    "Observation": 150,
    "MedicationRequest": 30,
    "Procedure": 20,
    "DiagnosticReport": 10,
    "Encounter": 1
  },
  "analysis_focus": "medication_interactions",
  "encounter_id": "encounter-uuid",
  "resource_types_included": ["Condition", "Observation", "MedicationRequest"],
  "provider_name": "Dr. John Smith",
  "appointment_date": "2024-01-15T10:30:00"
}
```

## Code Implementation

### SQLAlchemy Entity Mapping

**File**: `src/app/db/objects/entities/conversation_summaries.py`

```python
# Note: 'metadata' is reserved in SQLAlchemy, so we use 'summary_metadata' as the attribute name
summary_metadata = Column("metadata", JSON, nullable=True)
```

### Pydantic Model Mapping

**File**: `src/app/models/conversation_summaries.py`

```python
metadata: Optional[Dict[str, Any]] = Field(
    None, 
    alias="summaryMetadata",
    description="Additional metadata about the summary (e.g., source, analysis version)"
)
```

## API Implementations

### 1. Transcript Summarization API

**Endpoint**: `POST /care-capture/transcript-summarization`

**Source Value**: `"transcript"`

**Metadata Fields**:
- `source`: Always "transcript"
- `analysis_version`: Version of the analysis algorithm
- `transcript_count`: Number of transcripts processed

### 2. FHIR Analysis API

**Endpoint**: `POST /care-capture/fhir-analysis`

**Source Value**: `"fhir_analysis"`

**Metadata Fields**:
- `source`: Always "fhir_analysis"
- `analysis_version`: Version of the analysis algorithm
- `total_resources`: Total number of FHIR resources analyzed
- `resource_counts`: Breakdown by resource type
- `analysis_focus`: Optional focus area for analysis
- `encounter_id`: EHR encounter ID
- `resource_types_included`: List of FHIR resource types included
- `provider_name`: Provider name for the appointment
- `appointment_date`: Date of the appointment

### 3. Comprehensive Summarization API (Parallel Execution)

**Endpoint**: `POST /care-capture/comprehensive-summary`

**Source Values**: Multiple (`"transcript"` and/or `"fhir_analysis"`)

**Behavior**: 
- Executes transcript summarization and FHIR analysis **in parallel**
- Creates **separate summaries** for each data source
- Each summary has its own `metadata.source` value
- Returns array of summaries with distinct source tracking

**Result**:
One appointment can have multiple summaries created simultaneously:

```json
[
  {
    "id": "uuid-1",
    "appointment_id": "123e4567...",
    "metadata": {"source": "transcript", "transcript_count": 2},
    "summary_text": "Patient conversation summary..."
  },
  {
    "id": "uuid-2", 
    "appointment_id": "123e4567...",
    "metadata": {"source": "fhir_analysis", "total_resources": 352},
    "summary_text": "Clinical data analysis..."
  }
]
```

**Key Features**:
- ⚡ **Parallel Execution**: Both operations run concurrently
- 🛡️ **Partial Success**: Returns successful summaries even if one fails
- 📊 **Metrics**: Provides execution statistics
- 🔍 **Source Tracking**: Each summary clearly marked with its source

See [Comprehensive Summarization Documentation](./COMPREHENSIVE_SUMMARIZATION.md) for full details.

## Querying by Source

### Get all transcript summaries:
```sql
SELECT * FROM conversation_summaries 
WHERE metadata->>'source' = 'transcript';
```

### Get all FHIR analysis summaries:
```sql
SELECT * FROM conversation_summaries 
WHERE metadata->>'source' = 'fhir_analysis';
```

### Count summaries by source:
```sql
SELECT 
    metadata->>'source' as source_type,
    COUNT(*) as count
FROM conversation_summaries 
WHERE metadata IS NOT NULL
GROUP BY metadata->>'source';
```

### Get FHIR summaries with specific resource counts:
```sql
SELECT 
    id,
    appointment_id,
    metadata->'resource_counts'->>'Observation' as observation_count
FROM conversation_summaries 
WHERE metadata->>'source' = 'fhir_analysis'
AND (metadata->'resource_counts'->>'Observation')::int > 100;
```

### Get all summaries for an appointment (including multiple sources):
```sql
-- Returns all summaries for a single appointment
SELECT 
    id,
    appointment_id,
    metadata->>'source' as source_type,
    summary_text,
    created_at
FROM conversation_summaries 
WHERE appointment_id = '123e4567-e89b-12d3-a456-426614174000'
ORDER BY created_at DESC;

-- Result example:
-- id       | appointment_id | source_type    | summary_text         | created_at
-- uuid-1   | 123e4567...    | transcript     | Patient presents...  | 2024-01-15 10:05:00
-- uuid-2   | 123e4567...    | fhir_analysis  | Clinical data...     | 2024-01-15 10:05:05
```

### Get appointments with multiple summary types:
```sql
-- Find appointments that have both transcript and FHIR summaries
SELECT 
    appointment_id,
    COUNT(*) as summary_count,
    ARRAY_AGG(DISTINCT metadata->>'source') as sources
FROM conversation_summaries
WHERE metadata->>'source' IN ('transcript', 'fhir_analysis')
GROUP BY appointment_id
HAVING COUNT(DISTINCT metadata->>'source') > 1;

-- Result shows appointments with comprehensive summarization
-- appointment_id           | summary_count | sources
-- 123e4567...             | 2             | {transcript, fhir_analysis}
```

### Get latest summary by source for each appointment:
```sql
-- Useful for displaying the most recent summary of each type
WITH ranked_summaries AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (
            PARTITION BY appointment_id, metadata->>'source' 
            ORDER BY created_at DESC
        ) as rn
    FROM conversation_summaries
    WHERE metadata->>'source' IS NOT NULL
)
SELECT 
    appointment_id,
    metadata->>'source' as source_type,
    summary_text,
    created_at
FROM ranked_summaries
WHERE rn = 1
ORDER BY appointment_id, source_type;
```

## Best Practices

1. **Always include metadata** when creating summaries through any API
2. **Include analysis_version** to track algorithm changes over time
3. **Store source-specific context** in metadata (e.g., resource counts for FHIR, transcript count for transcripts)
4. **Use upsert operation** to handle updates to existing summaries
5. **Maintain consistency** between all APIs in terms of metadata structure
6. **Use metadata.source for filtering** in client applications to display different summary types
7. **Handle NULL metadata gracefully** for backwards compatibility with old summaries
8. **Index metadata->>'source'** for faster queries if querying by source frequently

### Frontend Best Practices

```javascript
// ✅ DO: Filter by source for better UX
const response = await api.getByAppointmentId(appointmentId);
const transcriptSummary = response.find(s => s.metadata?.source === 'transcript');
const clinicalSummary = response.find(s => s.metadata?.source === 'fhir_analysis');

// Display in separate sections
displaySection('Conversation Summary', transcriptSummary);
displaySection('Clinical Analysis', clinicalSummary);

// ✅ DO: Handle missing metadata
const source = summary.metadata?.source || 'unknown';

// ❌ DON'T: Assume single summary per appointment
const summary = response[0]; // Wrong! May have multiple summaries
```

## Migration Notes

- The `metadata` column already exists in the production database (`care-capture-app-dev`)
- No migration is required for existing data
- Existing summaries without metadata will have `NULL` in the metadata column
- New summaries will automatically include metadata based on their source

## Testing

Run the test script to verify the implementation:

```bash
python test_metadata_implementation.py
```

This will:
1. Verify the metadata column exists
2. List existing summaries with metadata
3. Count summaries by source type
4. Show total summary count

## Performance Optimization

### Optional Index for Source Queries

If you frequently query by `metadata.source`, add an index:

```sql
-- Create GIN index on metadata column (supports all JSON queries)
CREATE INDEX idx_conversation_summaries_metadata 
ON conversation_summaries USING GIN (metadata);

-- Or create functional index for specific source queries
CREATE INDEX idx_conversation_summaries_metadata_source 
ON conversation_summaries ((metadata->>'source'));

-- Verify index usage
EXPLAIN ANALYZE
SELECT * FROM conversation_summaries 
WHERE metadata->>'source' = 'transcript';
```

**Benefits:**
- ✅ Faster filtering by source type
- ✅ Faster COUNT queries by source
- ✅ Better performance for composite appointment + source queries

**Trade-offs:**
- ❌ Slightly slower INSERT/UPDATE operations
- ❌ Additional storage space (~10-15% of table size)

**Recommendation:** Add index if:
- Querying by source frequently (>1000 queries/day)
- Table has >10,000 summaries
- Query performance is critical

## Related Documentation

- [Comprehensive Summarization](./COMPREHENSIVE_SUMMARIZATION.md) - Parallel execution endpoint
- [Architecture](./ARCHITECTURE.md) - Service layer design
- [Breaking Changes Analysis](./BREAKING_CHANGES_ANALYSIS.md) - Compatibility info
- [API Examples](./API_EXAMPLES.md) - Code examples

