# Encounter Clinical Data Query Documentation

## Quick Start

**Run the test:**
```bash
cd /home/nithin/Project/care-capture-fastapi
poetry run python test_encounter_clinical_data.py
```

**Or use the quick test script:**
```bash
./test_encounter_quick.sh
```

---

## What This Does

Fetches all clinical data related to an encounter/appointment by querying:

1. **The Encounter resource itself** - where `resource_type = 'Encounter'` and `ehr_resource_id = '97953483'`
2. **All clinical resources that reference it** - where `data->>'encounterReference' = 'Encounter/97953483'`

This includes: Observations, Conditions, Procedures, MedicationRequests, DiagnosticReports, DocumentReferences, and CarePlans.

---

## Files in This Documentation

### 1. ENCOUNTER_QUERY_SUMMARY.md
**Quick executive summary** with test results and usage examples.

**Best for:** Getting started, understanding what was implemented

### 2. encounter_clinical_data_query_comparison.md
**Detailed comparison** between Node.js and FastAPI implementations.

**Best for:** Understanding implementation differences, performance characteristics

### 3. encounter_clinical_data_queries.sql
**11 SQL query examples** with comments and test data.

**Best for:** Database queries, SQL reference, performance optimization

---

## Reference Implementation

**Node.js (TypeScript):**
```
/home/nithin/Project/care-capture-nodeapi/src/modules/fhir-resources/services/
encounter-clinical-data.service.ts
```

**FastAPI (Python):**
```
/home/nithin/Project/care-capture-fastapi/src/app/db/objects/repositories/
fhir_resources.py
```

**Methods:**
- `get_encounter_with_clinical_data()` - Main query (encounter + clinical data)
- `get_resource_counts_by_encounter()` - Count resources by type
- `get_by_encounter()` - Clinical resources only (no encounter)

---

## Quick Reference

### Usage
```python
from src.app.db.objects.repositories.fhir_resources import FhirResourcesRepository

# Get all clinical data
resources = await fhir_repo.get_encounter_with_clinical_data(
    user_id="user-123",
    encounter_id="97953483",  # or "Encounter/97953483"
    resource_types=["Observation", "Condition"]  # optional
)

# Get counts
counts = await fhir_repo.get_resource_counts_by_encounter(
    user_id="user-123",
    encounter_id="97953483"
)
```

### Core SQL Pattern
```sql
SELECT * FROM fhir_resources
WHERE user_id = :user_id
  AND (
    (resource_type = 'Encounter' AND ehr_resource_id = '97953483')
    OR
    (data->>'encounterReference' = 'Encounter/97953483')
  )
```

---

## Test Data

**Database:** AWS RDS PostgreSQL (`care-capture-app-dev`)  
**Test User:** `abd7741f-35f1-4cc1-8d57-471921171c04`  
**Test Encounter:** `97953483` (352 total resources)

**Breakdown:**
- Encounter: 1
- Condition: 171
- DocumentReference: 96
- Observation: 67
- CarePlan: 9
- DiagnosticReport: 8

---

## Key Features

✅ **Single Query:** More efficient than Node.js multi-query approach  
✅ **Flexible Filtering:** Optional resource_types parameter  
✅ **ID Normalization:** Handles both "97953483" and "Encounter/97953483"  
✅ **Comprehensive:** Returns encounter + all linked clinical resources  
✅ **Production Tested:** All tests passing against AWS RDS  

---

## Performance Notes

**FastAPI vs Node.js:**
- FastAPI: 1 database query
- Node.js: 7+ database queries

**Recommendation:** Consider adding a GIN index for better JSONB query performance:
```sql
CREATE INDEX idx_fhir_resources_encounter_reference 
ON fhir_resources ((data->>'encounterReference'));
```

---

## Next Steps

1. ✅ Implementation complete
2. ✅ Tests passing
3. ✅ Documentation complete
4. 🔄 Consider adding the recommended index
5. 🔄 Monitor query performance in production

---

## Questions?

Refer to the detailed documentation files or run the test suite to see working examples.
